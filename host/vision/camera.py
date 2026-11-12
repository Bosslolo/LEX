"""Webcam person detect + opt-in face recognition."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from host.collector.state import PersonBox, StateHub
from host.vision.compare import build_comparison
from host.vision.faces import FaceGallery


ROOT = Path(__file__).resolve().parents[2]


class PersonCamera:
    def __init__(self, camera_index: int = 0, gallery: FaceGallery | None = None) -> None:
        self.camera_index = camera_index
        self.gallery = gallery or FaceGallery(
            root=ROOT / "data" / "faces",
            models_dir=ROOT / "data" / "models",
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._model = None
        self._cap = None
        self._latest_jpeg: bytes | None = None
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()

    def start(self, hub: StateHub, on_frame: Callable[[np.ndarray], None] | None = None) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, args=(hub, on_frame), daemon=True, name="person-camera"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass

    def latest_jpeg(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_jpeg

    def latest_frame_copy(self) -> np.ndarray | None:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def _ensure_model(self):
        if self._model is not None:
            return self._model if self._model is not False else None
        try:
            from ultralytics import YOLO

            self._model = YOLO("yolov8n.pt")
            return self._model
        except Exception:
            self._model = False
            return None

    def _loop(self, hub: StateHub, on_frame: Callable[[np.ndarray], None] | None) -> None:
        try:
            import cv2
        except Exception:
            hub.update(camera_ok=False, camera_count=0, people=[])
            return

        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            hub.update(camera_ok=False, camera_count=0, people=[])
            return

        # Prefer a sane capture size; some webcams open at 4K
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        model = self._ensure_model()
        hub.update(camera_ok=True, face_gallery=self.gallery.list_enrolled())

        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok:
                hub.update(camera_ok=False)
                time.sleep(0.2)
                continue

            # Downscale for detect speed on CPU
            h0, w0 = frame.shape[:2]
            if w0 > 1280:
                scale = 1280 / w0
                frame = cv2.resize(frame, (1280, int(h0 * scale)))

            # Keep a clean copy for enroll (no boxes/labels on the face)
            clean = frame.copy()
            people: list[PersonBox] = []
            named: list[str] = []

            # Face recognition (opt-in gallery)
            try:
                hits = self.gallery.recognize(clean)
            except Exception:
                hits = []
            for hit in hits:
                named.append(hit.name)
                people.append(
                    PersonBox(
                        id=len(people) + 1,
                        x=hit.x,
                        y=hit.y,
                        conf=hit.score,
                        name=hit.name,
                        source="face",
                    )
                )
                x1, y1, x2, y2 = hit.box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 210, 255), 2)
                cv2.putText(
                    frame,
                    hit.name,
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 210, 255),
                    2,
                )

            # YOLO person boxes (fill gaps / unnamed bodies)
            if model:
                try:
                    results = model.predict(clean, verbose=False, classes=[0], conf=0.45, imgsz=640)
                    h, w = clean.shape[:2]
                    for r in results:
                        if r.boxes is None:
                            continue
                        for box in r.boxes:
                            xyxy = box.xyxy[0].tolist()
                            conf = float(box.conf[0])
                            x1, y1, x2, y2 = xyxy
                            cx = ((x1 + x2) / 2) / max(1, w)
                            cy = ((y1 + y2) / 2) / max(1, h)
                            # Face center is near the head; YOLO center is mid-torso —
                            # match mainly on X so one person isn't double-counted.
                            if any(abs(cx - p.x) < 0.14 for p in people if p.name):
                                continue
                            people.append(
                                PersonBox(
                                    id=len(people) + 1,
                                    x=cx,
                                    y=cy,
                                    conf=conf,
                                    name="",
                                    source="camera",
                                )
                            )
                            cv2.rectangle(
                                frame,
                                (int(x1), int(y1)),
                                (int(x2), int(y2)),
                                (80, 220, 120),
                                2,
                            )
                            cv2.putText(
                                frame,
                                f"P{len(people)}",
                                (int(x1), max(20, int(y1) - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6,
                                (80, 220, 120),
                                2,
                            )
                except Exception:
                    pass

            snap = hub.snapshot()
            ble_names = [d.get("name") or "" for d in (snap.get("devices") or [])]
            comparison = build_comparison(
                csi_presence=float(snap.get("csi_presence") or 0),
                csi_motion=float(snap.get("csi_motion") or 0),
                csi_near_side=str(snap.get("near_side") or "none"),
                camera_ok=True,
                camera_count=len(people),
                named_faces=named,
                ble_count=int(snap.get("ble_count") or 0),
                ble_names=ble_names,
            )

            ok_jpg, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            with self._frame_lock:
                self._latest_frame = clean
                self._latest_jpeg = buf.tobytes() if ok_jpg else None

            hub.update(
                camera_ok=True,
                camera_count=len(people),
                people=people,
                named_faces=named,
                face_gallery=self.gallery.list_enrolled(),
                comparison=comparison,
            )
            if on_frame is not None:
                on_frame(frame)
            time.sleep(0.04)

        hub.update(camera_ok=False, camera_count=0, people=[], named_faces=[])


async def start_camera(
    hub: StateHub,
    camera_index: int = 0,
    gallery: FaceGallery | None = None,
) -> PersonCamera:
    cam = PersonCamera(camera_index=camera_index, gallery=gallery)
    cam.start(hub)
    await asyncio.sleep(0)
    return cam
