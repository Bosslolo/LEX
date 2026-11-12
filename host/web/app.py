"""FastAPI app: live room visualizer + face enroll + compare API."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from fastapi import Body, FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from host.collector.board_cmd import notify_calibrate, notify_led_sync, notify_mode
from host.collector.dsp import CsiDsp
from host.collector.ruview_bridge import run_ruview_bridge
from host.collector.sim import run_simulator
from host.collector.state import StateHub
from host.collector.udp_server import start_udp_server
from host.ruview_ui import serve_ruview_ui
from host.vision.camera import start_camera
from host.vision.faces import FaceGallery


ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / "static"


def create_app(
    hub: StateHub,
    dsp: CsiDsp,
    *,
    udp_host: str = "0.0.0.0",
    udp_port: int = 5005,
    enable_sim: bool = False,
    enable_camera: bool = True,
    camera_index: int = 0,
    ruview_url: str | None = None,
    enable_ruview_ui: bool = True,
    bind_host: str = "0.0.0.0",
    ruview_http_port: int = 3000,
    ruview_ws_port: int = 3001,
    lex_port: int = 8080,
) -> FastAPI:
    app = FastAPI(title="LEX WiFi CSI", version="0.2.0")
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
    gallery = FaceGallery(root=ROOT / "data" / "faces", models_dir=ROOT / "data" / "models")
    app.state.gallery = gallery
    app.state.ruview_http_port = ruview_http_port

    @app.on_event("startup")
    async def _startup() -> None:
        app.state.udp_transport = None
        app.state.ruview_task = None
        app.state.ruview_ui_task = None
        # External sensing-server owns UDP 5005 — bridge instead of binding.
        if ruview_url:
            app.state.ruview_task = asyncio.create_task(
                run_ruview_bridge(hub, url=ruview_url)
            )
            hub.update(mode="ruview-bridge", boards_ok=False)
        elif udp_port > 0:
            app.state.udp_transport, _ = await start_udp_server(udp_host, udp_port, dsp, hub)
        # Stock RuView UI on :3000 / WS :3001, fed from this hub (skip if
        # --ruview points at an external sensing-server that already serves UI).
        if enable_ruview_ui and not ruview_url:
            app.state.ruview_ui_task = asyncio.create_task(
                serve_ruview_ui(
                    hub,
                    bind_host=bind_host,
                    http_port=ruview_http_port,
                    ws_port=ruview_ws_port,
                    lex_port=lex_port,
                )
            )
        app.state.camera = None
        hub.update(face_gallery=gallery.list_enrolled())
        if enable_camera:
            try:
                app.state.camera = await start_camera(
                    hub, camera_index=camera_index, gallery=gallery
                )
            except Exception:
                hub.update(camera_ok=False)
        if enable_sim:
            app.state.sim_task = asyncio.create_task(run_simulator(dsp, hub))
        else:
            app.state.sim_task = None
        app.state.led_sync_task = asyncio.create_task(_led_sync_loop(hub))
        # Push lobby + sync once boards are likely online
        asyncio.create_task(_boot_lobby(hub))

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        transport = getattr(app.state, "udp_transport", None)
        if transport:
            transport.close()
        cam = getattr(app.state, "camera", None)
        if cam:
            cam.stop()
        for name in ("sim_task", "ruview_task", "ruview_ui_task", "led_sync_task"):
            task = getattr(app.state, name, None)
            if task:
                task.cancel()

    async def _boot_lobby(state_hub: StateHub) -> None:
        await asyncio.sleep(2.0)
        snap = state_hub.snapshot()
        await notify_mode(
            mode=str(snap.get("demo_mode") or "lobby"),
            tx_ip=snap.get("tx_ip") or None,
            rx_ip=snap.get("rx_ip") or None,
        )

    async def _led_sync_loop(state_hub: StateHub) -> None:
        while True:
            try:
                snap = state_hub.snapshot()
                if (snap.get("demo_mode") or "lobby") == "lobby":
                    await notify_led_sync(
                        tx_ip=snap.get("tx_ip") or None,
                        rx_ip=snap.get("rx_ip") or None,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(2.0)

    @app.get("/")
    async def lobby() -> FileResponse:
        return FileResponse(STATIC / "lobby.html")

    @app.get("/lex")
    async def lex_app() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/ruview")
    async def ruview_redirect(request: Request) -> RedirectResponse:
        # Full stock RuView UI (not a LEX reskin) — served on :3000.
        host = request.url.hostname or "127.0.0.1"
        port = getattr(app.state, "ruview_http_port", 3000)
        return RedirectResponse(url=f"http://{host}:{port}/")

    @app.get("/api/state")
    async def api_state() -> dict:
        return hub.snapshot()

    @app.get("/api/mode")
    async def api_mode_get() -> dict:
        snap = hub.snapshot()
        return {
            "ok": True,
            "mode": snap.get("demo_mode") or "lobby",
            "sent": getattr(app.state, "last_mode_sent", {}),
            "tx_ip": snap.get("tx_ip") or "",
            "rx_ip": snap.get("rx_ip") or "",
        }

    @app.post("/api/mode")
    async def api_mode_set(payload: dict = Body(default_factory=dict)) -> dict:
        mode = str((payload or {}).get("mode") or "lobby").strip().lower()
        if mode not in ("lobby", "lex", "ruview"):
            return {"ok": False, "error": "mode must be lobby|lex|ruview"}
        snap = hub.snapshot()
        sent = await notify_mode(
            mode=mode,
            tx_ip=snap.get("tx_ip") or None,
            rx_ip=snap.get("rx_ip") or None,
        )
        hub.update(demo_mode=mode)
        app.state.last_mode_sent = sent
        # Repeat shortly — school WiFi often drops the first UDP command
        async def _retry() -> None:
            await asyncio.sleep(0.35)
            await notify_mode(
                mode=mode,
                tx_ip=snap.get("tx_ip") or None,
                rx_ip=snap.get("rx_ip") or None,
            )

        asyncio.create_task(_retry())
        return {"ok": True, "mode": mode, "sent": sent}

    @app.post("/api/calibrate")
    async def api_calibrate(seconds: float = 60.0) -> dict:
        dsp.start_calibration(duration_s=seconds)
        hub.update(csi_calibrating=True, csi_calibrated=False)
        snap = hub.snapshot()
        led = await notify_calibrate(
            tx_ip=snap.get("tx_ip") or None,
            rx_ip=snap.get("rx_ip") or None,
            seconds=seconds,
        )
        return {"ok": True, "seconds": seconds, "led_blink": led}

    @app.post("/api/record/start")
    async def record_start(name: str = "demo") -> dict:
        path = hub.start_recording(name=name)
        return {"ok": True, "path": str(path)}

    @app.post("/api/record/stop")
    async def record_stop() -> dict:
        hub.stop_recording()
        return {"ok": True}

    @app.get("/api/faces")
    async def faces_list() -> dict:
        return {"ok": True, "faces": gallery.list_enrolled()}

    @app.post("/api/faces/enroll")
    async def faces_enroll(name: str = Form(...)) -> dict:
        cam = getattr(app.state, "camera", None)
        if cam is None:
            return {"ok": False, "error": "camera offline"}
        frame = cam.latest_frame_copy()
        if frame is None:
            return {"ok": False, "error": "no camera frame yet"}
        result = gallery.enroll_from_frame(frame, name)
        if result.get("ok"):
            hub.update(face_gallery=gallery.list_enrolled())
        return result

    @app.delete("/api/faces/{name}")
    async def faces_delete(name: str) -> dict:
        ok = gallery.delete(name)
        hub.update(face_gallery=gallery.list_enrolled())
        return {"ok": ok, "name": name}

    @app.get("/api/camera.jpg")
    async def camera_jpg() -> Response:
        cam = getattr(app.state, "camera", None)
        if cam is None:
            return Response(status_code=503)
        data = cam.latest_jpeg()
        if not data:
            return Response(status_code=503)
        return Response(content=data, media_type="image/jpeg")

    @app.get("/api/camera.mjpeg")
    async def camera_mjpeg() -> StreamingResponse:
        # Tiny JPEG so the browser always gets a first frame (cam may still be opening).
        placeholder = base64.b64decode(
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkS"
            "Ew8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJ"
            "CQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
            "MjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAA"
            "AAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAA"
            "AAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA8A/9k="
        )

        async def gen():
            boundary = b"--frame"
            while True:
                cam = getattr(app.state, "camera", None)
                data = cam.latest_jpeg() if cam else None
                if not data:
                    data = placeholder
                yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                await asyncio.sleep(0.08)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                if dsp.poll_calibration():
                    hub.update(
                        csi_calibrating=dsp.calibrating,
                        csi_calibrated=dsp.calibrated,
                    )
                hub.tick_liveness()
                await websocket.send_text(json.dumps(hub.snapshot()))
                await asyncio.sleep(0.05)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    return app
