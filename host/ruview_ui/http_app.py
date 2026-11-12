"""HTTP app: stock RuView UI static files + sensing/health/pose API stubs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from host.collector.state import StateHub
from host.ruview_ui.frame import hub_to_sensing_update, status_from_hub
from host.ruview_ui.pose import hub_to_pose_message

ROOT = Path(__file__).resolve().parents[2]
RUVIEW_UI = ROOT / "_ruview_ref" / "ui"

_LOBBY_CHIP = """
<style>
#lex-lobby-chip{position:fixed;bottom:14px;left:14px;z-index:99999;font:600 12px/1.25 system-ui,sans-serif;
display:flex;flex-direction:column;gap:6px;max-width:280px}
#lex-lobby-chip a,#lex-lobby-chip span{display:inline-block;padding:10px 14px;border-radius:999px;background:#0b1220;color:#7dd3fc;
text-decoration:none;border:1px solid rgba(125,211,252,.35);box-shadow:0 8px 24px rgba(0,0,0,.35)}
#lex-lobby-chip a:hover{background:#111827;color:#fff}
#lex-lobby-chip .note{border-radius:12px;color:#cbd5e1;font-weight:500;opacity:.95}
</style>
<div id="lex-lobby-chip">
  <a href="__LOBBY__">← LEX lobby</a>
  <span class="note">Signal-derived · 2 LEX nodes (not a DensePose .rvf model). Avoid the orange Demo button — that invents stick figures.</span>
</div>
"""

def _with_lobby_chip(html: str, lobby_url: str) -> str:
    chip = _LOBBY_CHIP.replace("__LOBBY__", lobby_url)
    if "</body>" in html:
        return html.replace("</body>", chip + "</body>")
    return html + chip


def build_http_app(hub: StateHub, *, lex_port: int = 8080) -> FastAPI:
    app = FastAPI(title="RuView UI (LEX dual)", version="0.1.0")
    app.state.lex_port = lex_port

    # ---- health -----------------------------------------------------------
    @app.get("/health/live")
    async def health_live() -> dict:
        return {"status": "alive", "lex_dual": True}

    @app.get("/health/ready")
    async def health_ready() -> dict:
        snap = hub.snapshot()
        return {
            "status": "ready",
            "boards_ok": bool(snap.get("boards_ok")),
            "lex_dual": True,
        }

    @app.get("/health/health")
    async def health_system() -> dict:
        snap = hub.snapshot()
        live = bool(snap.get("boards_ok")) or float(snap.get("csi_pps") or 0) > 0.5
        return {
            "status": "healthy",
            "timestamp": snap.get("ts"),
            "components": {
                "api": {"status": "up", "message": "LEX dual RuView API"},
                "hardware": {
                    "status": "up" if live else "degraded",
                    "message": "ESP boards via LEX collector" if live else "waiting for CSI",
                },
                "inference": {"status": "up", "message": "LEX CSI → RuView frames"},
                "streaming": {"status": "up", "message": "pose :3000 + sensing :3001"},
            },
        }

    @app.get("/health/version")
    async def health_version() -> dict:
        return {"version": "lex-dual", "name": "RuView UI via LEX"}

    @app.get("/health/metrics")
    async def health_metrics() -> dict:
        snap = hub.snapshot()
        return {
            "csi_pps": snap.get("csi_pps"),
            "csi_motion": snap.get("csi_motion"),
            "boards_ok": snap.get("boards_ok"),
        }

    # ---- core API ---------------------------------------------------------
    @app.get("/api/v1/info")
    async def api_info() -> dict:
        return {
            "name": "RuView (LEX dual)",
            "version": "lex-dual",
            "environment": "school-demo",
            "features": {
                "pose_estimation": True,
                "streaming": True,
                "sensing": True,
                "lex_bridge": True,
            },
        }

    @app.get("/api/v1/status")
    async def api_status() -> dict:
        return status_from_hub(hub.snapshot())

    @app.get("/api/v1/sensing/latest")
    async def sensing_latest() -> dict:
        return hub_to_sensing_update(hub.snapshot())

    @app.get("/api/v1/pose/current")
    async def pose_current() -> dict:
        msg = hub_to_pose_message(hub.snapshot())
        persons = ((msg.get("data") or {}).get("pose") or {}).get("persons") or []
        return {
            "timestamp": msg.get("timestamp"),
            "persons": persons,
            "zone_id": "school-room",
            "total_detections": len(persons),
        }

    @app.get("/api/v1/pose/zones/summary")
    async def pose_zones() -> dict:
        persons = (
            ((hub_to_pose_message(hub.snapshot()).get("data") or {}).get("pose") or {}).get("persons")
            or []
        )
        return {"zones": {"school-room": len(persons)}}

    @app.get("/api/v1/pose/stats")
    async def pose_stats() -> dict:
        frame = hub_to_sensing_update(hub.snapshot())
        n = frame.get("estimated_persons") or 0
        return {
            "total_detections": n,
            "average_confidence": (frame.get("classification") or {}).get("confidence") or 0,
            "peak_persons": n,
            "hours_analyzed": 0,
        }

    @app.get("/api/v1/pose/activities")
    async def pose_activities() -> dict:
        return {"activities": []}

    @app.post("/api/v1/pose/calibrate")
    async def pose_calibrate() -> dict:
        return {"ok": True, "message": "Calibration owned by LEX /api/calibrate"}

    @app.get("/api/v1/pose/calibration/status")
    async def pose_cal_status() -> dict:
        snap = hub.snapshot()
        return {
            "calibrating": bool(snap.get("csi_calibrating")),
            "calibrated": bool(snap.get("csi_calibrated")),
        }

    @app.get("/api/v1/stream/status")
    async def stream_status() -> dict:
        return {"is_active": True, "connected_clients": 1, "messages_sent": 0, "uptime": 0}

    @app.post("/api/v1/stream/start")
    async def stream_start() -> dict:
        return {"message": "Streaming active (LEX dual)", "status": "active"}

    @app.post("/api/v1/stream/stop")
    async def stream_stop() -> dict:
        return {"message": "Streaming stays on in dual mode", "status": "active"}

    # ---- models / train / recording stubs (silence UI 404 spam) -----------
    # DensePose .rvf models need 4+ CSI nodes + a trained weights file.
    # With 2 LEX boards we stay on signal-derived mode — no fake "active model".
    @app.get("/api/v1/models")
    async def models_list() -> dict:
        return {"models": []}

    @app.get("/api/v1/models/active")
    async def models_active() -> Response:
        return Response(status_code=404, content='{"detail":"no model loaded"}', media_type="application/json")

    @app.get("/api/v1/models/lora/profiles")
    async def lora_profiles() -> dict:
        return {"profiles": []}

    @app.post("/api/v1/models/load")
    async def models_load() -> dict:
        return {"ok": True, "model_id": "lex-csi"}

    @app.post("/api/v1/models/unload")
    async def models_unload() -> dict:
        return {"ok": True}

    @app.post("/api/v1/models/lora/activate")
    async def lora_activate() -> dict:
        return {"ok": False, "error": "LoRA not available in LEX dual mode"}

    @app.get("/api/v1/models/{model_id}")
    async def models_get(model_id: str) -> dict:
        return {"id": model_id, "name": model_id, "active": model_id == "lex-csi"}

    @app.delete("/api/v1/models/{model_id}")
    async def models_delete(model_id: str) -> dict:
        return {"ok": False, "error": "models are read-only in LEX dual mode"}

    @app.get("/api/v1/train/status")
    async def train_status() -> dict:
        return {"status": "idle", "running": False, "lex_dual": True}

    @app.post("/api/v1/train/start")
    @app.post("/api/v1/train/stop")
    @app.post("/api/v1/train/pretrain")
    @app.post("/api/v1/train/lora")
    async def train_noop() -> dict:
        return {"ok": False, "error": "training disabled in LEX dual mode"}

    @app.get("/api/v1/recording/list")
    async def recording_list() -> dict:
        return {"recordings": []}

    @app.post("/api/v1/recording/start")
    @app.post("/api/v1/recording/stop")
    async def recording_noop() -> dict:
        return {"ok": False, "error": "use LEX /api/record/* for captures"}

    @app.delete("/api/v1/recording/{rec_id}")
    async def recording_delete(rec_id: str) -> dict:
        return {"ok": False, "error": "not found"}

    @app.get("/oauth/status")
    async def oauth_status() -> dict:
        return {"enabled": False, "authenticated": False, "lex_dual": True}

    # ---- Live Demo pose WebSocket (same origin :3000) ---------------------
    @app.websocket("/api/v1/stream/pose")
    async def ws_pose(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connection_established",
                    "payload": {"client_id": "lex-dual", "lex_dual": True},
                }
            )
        )
        try:
            while True:
                msg = hub_to_pose_message(hub.snapshot())
                await websocket.send_text(json.dumps(msg))
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    @app.websocket("/api/v1/stream/events")
    async def ws_events(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await asyncio.sleep(5.0)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "system_event",
                            "payload": {
                                "event_type": "heartbeat",
                                "zone_id": "school-room",
                                "timestamp": hub.snapshot().get("ts"),
                            },
                        }
                    )
                )
        except WebSocketDisconnect:
            return
        except Exception:
            return

    # ---- UI ---------------------------------------------------------------
    index = RUVIEW_UI / "index.html"
    if not index.is_file():
        raise FileNotFoundError(f"RuView UI missing: {index}")

    def _lobby_url(request: Request) -> str:
        host = request.url.hostname or "127.0.0.1"
        port = getattr(app.state, "lex_port", 8080)
        return f"http://{host}:{port}/"

    def _index_html(request: Request) -> HTMLResponse:
        raw = index.read_text(encoding="utf-8")
        return HTMLResponse(_with_lobby_chip(raw, _lobby_url(request)))

    @app.get("/")
    async def root_index(request: Request) -> Response:
        return _index_html(request)

    @app.get("/ui")
    @app.get("/ui/")
    async def ui_index() -> RedirectResponse:
        return RedirectResponse(url="/ui/index.html")

    @app.get("/ui/index.html")
    async def ui_index_file(request: Request) -> Response:
        return _index_html(request)

    app.mount("/ui", StaticFiles(directory=str(RUVIEW_UI), html=True), name="ruview-ui-prefixed")
    app.mount("/", StaticFiles(directory=str(RUVIEW_UI), html=True), name="ruview-ui")

    return app
