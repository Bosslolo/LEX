"""Opt-in face gallery using OpenCV YuNet + SFace (no cloud)."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())[:48]
    return s or "person"


@dataclass
class FaceHit:
    name: str
    score: float
    x: float
    y: float
    box: tuple[int, int, int, int]


class FaceGallery:
    def __init__(self, root: Path, models_dir: Path) -> None:
        self.root = root
        self.models_dir = models_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._detector = None
        self._recognizer = None
        self._db: dict[str, np.ndarray] = {}
        self._load_db()

    @property
    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._db.keys())

    def _ensure_models(self, frame_w: int, frame_h: int) -> bool:
        if self._detector is not None and self._recognizer is not None:
            try:
                self._detector.setInputSize((frame_w, frame_h))
            except Exception:
                pass
            return True
        try:
            import cv2

            yunet = self.models_dir / "face_detection_yunet_2023mar.onnx"
            sface = self.models_dir / "face_recognition_sface_2021dec.onnx"
            if not yunet.exists() or not sface.exists():
                return False
            self._detector = cv2.FaceDetectorYN.create(
                str(yunet), "", (frame_w, frame_h), 0.7, 0.3, 5000
            )
            self._recognizer = cv2.FaceRecognizerSF.create(str(sface), "")
            return True
        except Exception:
            self._detector = None
            self._recognizer = None
            return False

    def _load_db(self) -> None:
        self._db.clear()
        for meta in self.root.glob("*/meta.json"):
            try:
                info = json.loads(meta.read_text(encoding="utf-8"))
                name = str(info.get("name") or meta.parent.name)
                emb_path = meta.parent / "embedding.npy"
                if emb_path.exists():
                    self._db[name] = np.load(emb_path)
            except Exception:
                continue

    def list_enrolled(self) -> list[dict[str, Any]]:
        out = []
        for name in self.names:
            folder = self.root / _slug(name)
            out.append(
                {
                    "name": name,
                    "slug": _slug(name),
                    "has_photo": (folder / "face.jpg").exists(),
                }
            )
        return out

    def delete(self, name: str) -> bool:
        import shutil

        with self._lock:
            self._db.pop(name, None)
            folder = self.root / _slug(name)
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
                return True
        return False

    def _best_face(self, frame: np.ndarray):
        import cv2

        h, w = frame.shape[:2]
        if not self._ensure_models(w, h):
            return None, None
        assert self._detector is not None and self._recognizer is not None
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(frame)
        if faces is None or len(faces) == 0:
            return None, None
        # largest face
        faces = sorted(faces, key=lambda f: float(f[2] * f[3]), reverse=True)
        face = faces[0]
        aligned = self._recognizer.alignCrop(frame, face)
        feat = self._recognizer.feature(aligned)
        x, y, bw, bh = [int(v) for v in face[:4]]
        return feat, (x, y, x + bw, y + bh)

    def enroll_from_frame(self, frame: np.ndarray, name: str) -> dict[str, Any]:
        import cv2

        name = name.strip()
        if not name:
            return {"ok": False, "error": "name required"}
        feat, box = self._best_face(frame)
        if feat is None or box is None:
            return {"ok": False, "error": "no face found — look at camera"}
        folder = self.root / _slug(name)
        folder.mkdir(parents=True, exist_ok=True)
        x1, y1, x2, y2 = box
        crop = frame[max(0, y1) : max(0, y2), max(0, x1) : max(0, x2)]
        if crop.size:
            cv2.imwrite(str(folder / "face.jpg"), crop)
        np.save(folder / "embedding.npy", feat)
        (folder / "meta.json").write_text(
            json.dumps({"name": name, "consent": True}, indent=2), encoding="utf-8"
        )
        with self._lock:
            self._db[name] = feat
        return {"ok": True, "name": name, "box": box}

    def recognize(self, frame: np.ndarray, threshold: float = 0.36) -> list[FaceHit]:
        """Return named face hits in normalized room coords (x,y in 0..1)."""
        import cv2

        h, w = frame.shape[:2]
        if not self._ensure_models(w, h):
            return []
        assert self._detector is not None and self._recognizer is not None
        with self._lock:
            db = dict(self._db)
        if not db:
            return []

        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(frame)
        if faces is None:
            return []

        hits: list[FaceHit] = []
        for face in faces:
            aligned = self._recognizer.alignCrop(frame, face)
            feat = self._recognizer.feature(aligned)
            best_name = ""
            best_score = -1.0
            for name, ref in db.items():
                # cosine similarity (higher = better for SFace match)
                score = float(self._recognizer.match(feat, ref, cv2.FaceRecognizerSF_FR_COSINE))
                if score > best_score:
                    best_score = score
                    best_name = name
            if best_score >= threshold and best_name:
                x, y, bw, bh = [float(v) for v in face[:4]]
                cx = (x + bw / 2) / max(1, w)
                cy = (y + bh / 2) / max(1, h)
                hits.append(
                    FaceHit(
                        name=best_name,
                        score=best_score,
                        x=cx,
                        y=cy,
                        box=(int(x), int(y), int(x + bw), int(y + bh)),
                    )
                )
        return hits
