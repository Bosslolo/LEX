"""FastAPI app: live room visualizer + face enroll + compare API."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from host.collector.board_cmd import notify_calibrate
from host.collector.dsp import CsiDsp
from host.collector.sim import run_simulator
from host.collector.state import StateHub
from host.collector.udp_server import start_udp_server
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
) -> FastAPI:
    app = FastAPI(title="LEX WiFi CSI", version="0.2.0")
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
    gallery = FaceGallery(root=ROOT / "data" / "faces", models_dir=ROOT / "data" / "models")
    app.state.gallery = gallery

    @app.on_event("startup")
    async def _startup() -> None:
        app.state.udp_transport, _ = await start_udp_server(udp_host, udp_port, dsp, hub)
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

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        transport = getattr(app.state, "udp_transport", None)
        if transport:
            transport.close()
        cam = getattr(app.state, "camera", None)
        if cam:
            cam.stop()
        task = getattr(app.state, "sim_task", None)
        if task:
            task.cancel()

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    async def api_state() -> dict:
        return hub.snapshot()

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
