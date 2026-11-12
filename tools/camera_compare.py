#!/usr/bin/env python3
"""
LEX camera ↔ CSI comparison baseline.

Primary: YOLO person count (works for ~20 people in a mid-size room).
Secondary: face *detection* count (not identity recognition — faces miss backs/side views).
CSI: polls RuView sensing-server /api/v1/sensing/latest.

Keys:
  q / Esc  quit
  s         snapshot compare row to CSV
  f         toggle face boxes
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "camera_compare"
PERSON_CLASS = 0  # COCO "person"


@dataclass
class CompareSample:
    ts: str
    camera_persons: int
    camera_faces: int
    csi_persons: int | None
    csi_presence: bool | None
    csi_motion: str | None
    csi_confidence: float | None
    csi_source: str | None
    event: str
    note: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_csi(url: str, timeout: float = 0.4) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return {}


def parse_csi(payload: dict) -> tuple[int | None, bool | None, str | None, float | None, str | None]:
    if not payload:
        return None, None, None, None, None
    cls = payload.get("classification") or {}
    persons = payload.get("estimated_persons")
    if persons is None:
        persons = len(payload.get("persons") or [])
    try:
        persons_i = int(persons)
    except (TypeError, ValueError):
        persons_i = None
    conf = cls.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None
    return (
        persons_i,
        cls.get("presence"),
        cls.get("motion_level"),
        conf_f,
        payload.get("source"),
    )


def classify_event(
    camera_n: int,
    faces: int,
    csi_n: int | None,
    motion: str | None,
    box_speeds: deque[float],
) -> tuple[str, str]:
    """Cheap 'something special' tags for the school baseline — not a full activity model."""
    avg_speed = sum(box_speeds) / len(box_speeds) if box_speeds else 0.0
    notes: list[str] = []

    if camera_n == 0:
        event = "empty"
    elif camera_n >= 12:
        event = "crowded"
        notes.append(f"{camera_n} people visible")
    elif avg_speed > 25:
        event = "high_motion"
        notes.append("boxes moving fast")
    elif motion in {"present_moving", "active"} and camera_n > 0:
        event = "active"
    else:
        event = "normal"

    if csi_n is not None and camera_n is not None:
        delta = camera_n - csi_n
        if abs(delta) >= 2:
            notes.append(f"CSI Δ {delta:+d} vs camera")
            if event == "normal":
                event = "mismatch"

    if faces > 0 and camera_n > 0 and faces < max(1, camera_n // 3):
        notes.append("few faces (many backs/side views)")

    return event, "; ".join(notes) if notes else ""


def smooth_count(history: deque[int]) -> int:
    if not history:
        return 0
    # Median of recent frames — kills single-frame flicker
    arr = sorted(history)
    return arr[len(arr) // 2]


def draw_panel(frame, sample: CompareSample, fps: float) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 110), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    csi_p = "—" if sample.csi_persons is None else str(sample.csi_persons)
    csi_src = sample.csi_source or "offline"
    lines = [
        f"CAMERA persons {sample.camera_persons}   faces {sample.camera_faces}   {fps:.1f} FPS",
        f"CSI     persons {csi_p}   presence {sample.csi_presence}   {sample.csi_motion or '—'}   ({csi_src})",
        f"EVENT   {sample.event}   {sample.note}",
    ]
    y = 28
    for line in lines:
        cv2.putText(frame, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (240, 240, 240), 2, cv2.LINE_AA)
        y += 28


def create_face_detector(width: int, height: int):
    """OpenCV 5 uses FaceDetectorYN; older OpenCV used Haar cascades."""
    # Prefer YuNet (OpenCV 4.5.1+ / 5.x)
    if hasattr(cv2, "FaceDetectorYN_create"):
        model = ROOT / "models" / "face_detection_yunet_2023mar.onnx"
        if not model.exists():
            model.parent.mkdir(parents=True, exist_ok=True)
            url = (
                "https://github.com/opencv/opencv_zoo/raw/main/models/"
                "face_detection_yunet/face_detection_yunet_2023mar.onnx"
            )
            print(f"Downloading YuNet face model → {model}")
            try:
                urllib.request.urlretrieve(url, model)
            except Exception as exc:
                print(f"YuNet download failed ({exc}); faces disabled")
                return None
        det = cv2.FaceDetectorYN_create(str(model), "", (width, height), 0.7, 0.3, 5000)
        return ("yunet", det)

    # Legacy Haar (OpenCV 4.x)
    if hasattr(cv2, "CascadeClassifier"):
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(str(cascade_path))
        if not cascade.empty():
            return ("haar", cascade)
    return None


def detect_faces(detector, frame) -> list[tuple[int, int, int, int]]:
    if detector is None:
        return []
    kind, obj = detector
    h, w = frame.shape[:2]
    if kind == "yunet":
        obj.setInputSize((w, h))
        _retval, faces = obj.detect(frame)
        if faces is None:
            return []
        out = []
        for f in faces:
            x, y, fw, fh = map(int, f[:4])
            out.append((x, y, fw, fh))
        return out
    # haar
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    raw = obj.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(40, 40))
    return [(int(x), int(y), int(ww), int(hh)) for (x, y, ww, hh) in raw]


def open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    # AVFoundation is the right backend on modern macOS
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise SystemExit(
            f"Cannot open camera index {index}. Grant Camera access to Terminal/Cursor "
            "in System Settings → Privacy & Security → Camera."
        )
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def main() -> None:
    ap = argparse.ArgumentParser(description="LEX camera vs CSI comparison baseline")
    ap.add_argument("--camera", type=int, default=0, help="Camera index (0=FaceTime, try 1 for Continuity/iPhone)")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--imgsz", type=int, default=640, help="YOLO inference size")
    ap.add_argument("--conf", type=float, default=0.35, help="Person confidence threshold")
    ap.add_argument("--every", type=int, default=2, help="Run YOLO every N frames (smoothness)")
    ap.add_argument("--csi-url", default="http://127.0.0.1:3000/api/v1/sensing/latest")
    ap.add_argument("--model", default="yolov8n.pt", help="Ultralytics model (nano = fast)")
    ap.add_argument("--no-faces", action="store_true", help="Disable face detection overlay")
    ap.add_argument("--headless", action="store_true", help="No window; still write JSON/CSV")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "compare_log.csv"
    latest_path = args.out / "latest.json"

    from ultralytics import YOLO

    print(f"Loading {args.model} …")
    model = YOLO(args.model)

    face_detector = None
    show_faces = not args.no_faces
    if show_faces:
        face_detector = create_face_detector(args.width, args.height)
        if face_detector is None:
            print("Face detector unavailable — continuing with person count only")

    cap = open_camera(args.camera, args.width, args.height)

    count_hist: deque[int] = deque(maxlen=7)
    face_hist: deque[int] = deque(maxlen=7)
    speed_hist: deque[float] = deque(maxlen=15)
    prev_centroids: list[tuple[float, float]] = []
    last_boxes: list = []
    last_faces: list = []
    frame_i = 0
    fps_ema = 0.0
    t_prev = time.time()

    new_csv = not csv_path.exists()
    csv_file = open(csv_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=list(CompareSample.__annotations__.keys()))
    if new_csv:
        writer.writeheader()

    print("Running. q=quit  s=save row  f=toggle faces")
    print(f"Logging → {csv_path}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame grab failed")
                time.sleep(0.05)
                continue

            frame_i += 1
            run_det = frame_i % max(1, args.every) == 0

            if run_det:
                # Person detection
                results = model.predict(
                    frame,
                    imgsz=args.imgsz,
                    conf=args.conf,
                    classes=[PERSON_CLASS],
                    verbose=False,
                )
                boxes = []
                centroids = []
                r0 = results[0]
                if r0.boxes is not None:
                    for b in r0.boxes:
                        xyxy = b.xyxy[0].cpu().numpy()
                        x1, y1, x2, y2 = map(int, xyxy)
                        boxes.append((x1, y1, x2, y2, float(b.conf[0])))
                        centroids.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
                last_boxes = boxes

                # Crude motion from centroid shifts
                if prev_centroids and centroids:
                    dists = []
                    for c in centroids:
                        dmin = min(((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2) ** 0.5 for p in prev_centroids)
                        dists.append(dmin)
                    speed_hist.append(float(np.median(dists)) if dists else 0.0)
                prev_centroids = centroids

                # Faces (secondary — not recognition)
                faces = detect_faces(face_detector, frame) if (show_faces and face_detector) else []
                last_faces = faces

                count_hist.append(len(boxes))
                face_hist.append(len(faces))

            cam_n = smooth_count(count_hist)
            face_n = smooth_count(face_hist)

            csi = fetch_csi(args.csi_url)
            csi_n, csi_pres, csi_mot, csi_conf, csi_src = parse_csi(csi)
            event, note = classify_event(cam_n, face_n, csi_n, csi_mot, speed_hist)

            sample = CompareSample(
                ts=utc_now(),
                camera_persons=cam_n,
                camera_faces=face_n,
                csi_persons=csi_n,
                csi_presence=csi_pres,
                csi_motion=csi_mot,
                csi_confidence=csi_conf,
                csi_source=csi_src,
                event=event,
                note=note,
            )

            # Draw
            for (x1, y1, x2, y2, conf) in last_boxes:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 220, 120), 2)
                cv2.putText(frame, f"{conf:.2f}", (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 220, 120), 1)
            if show_faces:
                for (x, y, w, h) in last_faces:
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (80, 180, 255), 2)

            now = time.time()
            inst = 1.0 / max(1e-3, now - t_prev)
            t_prev = now
            fps_ema = inst if fps_ema == 0 else (fps_ema * 0.9 + inst * 0.1)
            draw_panel(frame, sample, fps_ema)

            latest_path.write_text(json.dumps(asdict(sample), indent=2), encoding="utf-8")

            # Append a CSV row ~1 Hz
            if frame_i % max(1, int(fps_ema or 15)) == 0:
                writer.writerow(asdict(sample))
                csv_file.flush()

            if not args.headless:
                cv2.imshow("LEX camera ↔ CSI compare", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("s"):
                    writer.writerow(asdict(sample))
                    csv_file.flush()
                    print("saved row", sample)
                if key == ord("f"):
                    show_faces = not show_faces
                    print("faces", "on" if show_faces else "off")
            else:
                if frame_i % 30 == 0:
                    print(asdict(sample))
                time.sleep(0.001)

    finally:
        csv_file.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
