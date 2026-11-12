#!/usr/bin/env python3
"""List OpenCV camera indexes that open on this Mac (FaceTime vs Continuity/iPhone)."""

from __future__ import annotations

import cv2


def main() -> None:
    print("Probing camera indexes 0–5 (grant Camera access to Terminal if asked)…\n")
    found = False
    for i in range(6):
        cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
        ok = cap.isOpened()
        w = h = 0
        if ok:
            ok_frame, frame = cap.read()
            if ok_frame and frame is not None:
                h, w = frame.shape[:2]
            else:
                ok = False
        cap.release()
        if ok:
            found = True
            hint = "← usually Mac FaceTime" if i == 0 else "← try this for Continuity / iPhone"
            print(f"  index {i}: OK  {w}x{h}  {hint}")
        else:
            print(f"  index {i}: —")
    if not found:
        print("\nNo cameras opened. System Settings → Privacy & Security → Camera → enable Terminal.")
    else:
        print("\nDemo: ./scripts/demo-start.sh")
        print("Phone cam: ./scripts/demo-start.sh --phone   # or --camera N from above")


if __name__ == "__main__":
    main()
