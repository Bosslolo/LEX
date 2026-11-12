"""Entry point: python -m host.main [--sim] [--no-camera]."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from host.collector.dsp import CsiDsp
from host.collector.state import StateHub
from host.web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="LEX WiFi CSI host")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--udp-port", type=int, default=5005)
    parser.add_argument("--sim", action="store_true", help="Synthetic CSI/BLE for UI demos")
    parser.add_argument("--no-camera", action="store_true")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--calibrate", type=float, default=0.0, help="Auto-start calibration seconds")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    hub = StateHub(replay_dir=root / "data" / "replays")
    dsp = CsiDsp()
    if args.calibrate > 0:
        dsp.start_calibration(duration_s=args.calibrate)

    app = create_app(
        hub,
        dsp,
        udp_port=args.udp_port,
        enable_sim=args.sim,
        enable_camera=not args.no_camera,
        camera_index=args.camera,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
