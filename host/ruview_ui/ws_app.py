"""WebSocket sensing stream on :3001 (stock RuView UI expects this port)."""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from host.collector.state import StateHub
from host.ruview_ui.frame import hub_to_sensing_update


def build_ws_app(hub: StateHub, *, hz: float = 10.0) -> FastAPI:
    app = FastAPI(title="RuView sensing WS", version="0.1.0")
    delay = 1.0 / max(1.0, hz)

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "ws": "/ws/sensing"}

    @app.websocket("/ws/sensing")
    async def ws_sensing(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                frame = hub_to_sensing_update(hub.snapshot())
                await websocket.send_text(json.dumps(frame))
                await asyncio.sleep(delay)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    return app
