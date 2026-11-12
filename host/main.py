"""Entry point: python -m host.main [--sim] [--no-camera]."""

from __future__ import annotations

import argparse
import atexit
import sys
from pathlib import Path

import uvicorn

from host.collector.dsp import CsiDsp
from host.collector.state import StateHub
from host.web.app import create_app


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
    except AttributeError:
        pass
    return False


def _acquire_single_instance(root: Path) -> None:
    """Prevent two host.main processes fighting over UDP 5005 / :8080 / :3000.

    Note: on Windows a venv `python.exe` launcher + child interpreter both show
    up as host.main — the lock stores the child pid that actually runs main().
    """
    lock_path = root / "data" / "host.main.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            old = int(lock_path.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            old = 0
        if _pid_alive(old):
            print(
                f"Another host.main is already running (pid {old}). Stop it first.",
                file=sys.stderr,
            )
            raise SystemExit(2)
    lock_path.write_text(str(__import__("os").getpid()), encoding="utf-8")

    def _clear() -> None:
        try:
            if lock_path.exists() and lock_path.read_text(encoding="utf-8").strip() == str(
                __import__("os").getpid()
            ):
                lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_clear)


def main() -> None:
    parser = argparse.ArgumentParser(description="LEX WiFi CSI host")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--udp-port", type=int, default=5005)
    parser.add_argument("--sim", action="store_true", help="Synthetic CSI/BLE for UI demos")
    parser.add_argument("--no-camera", action="store_true")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument(
        "--calibrate",
        type=float,
        default=20.0,
        help="Auto-start empty-room calibration seconds (0=skip). Default 20.",
    )
    parser.add_argument(
        "--ruview",
        nargs="?",
        const="http://127.0.0.1:3000/api/v1/sensing/latest",
        default=None,
        help="Mirror external RuView sensing-server into LEX (skip UDP bind). "
        "Optional URL, default http://127.0.0.1:3000/api/v1/sensing/latest. "
        "Disables the built-in RuView UI adapter (external server owns :3000).",
    )
    parser.add_argument(
        "--no-ruview-ui",
        action="store_true",
        help="Do not serve stock RuView UI on :3000 / sensing WS on :3001",
    )
    parser.add_argument("--ruview-http-port", type=int, default=3000)
    parser.add_argument("--ruview-ws-port", type=int, default=3001)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    _acquire_single_instance(root)
    hub = StateHub(replay_dir=root / "data" / "replays")
    dsp = CsiDsp()
    if args.calibrate > 0:
        dsp.start_calibration(duration_s=args.calibrate)

    app = create_app(
        hub,
        dsp,
        udp_port=0 if args.ruview else args.udp_port,
        enable_sim=args.sim,
        enable_camera=not args.no_camera,
        camera_index=args.camera,
        ruview_url=args.ruview,
        enable_ruview_ui=not args.no_ruview_ui and not args.ruview,
        bind_host=args.host,
        ruview_http_port=args.ruview_http_port,
        ruview_ws_port=args.ruview_ws_port,
        lex_port=args.port,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
