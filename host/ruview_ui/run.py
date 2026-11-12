"""Run RuView HTTP (:3000) + sensing WebSocket (:3001) alongside LEX."""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from host.collector.state import StateHub
from host.ruview_ui.http_app import build_http_app
from host.ruview_ui.ws_app import build_ws_app

log = logging.getLogger("lex.ruview_ui")


async def serve_ruview_ui(
    hub: StateHub,
    *,
    bind_host: str = "0.0.0.0",
    http_port: int = 3000,
    ws_port: int = 3001,
    lex_port: int = 8080,
    hz: float = 10.0,
) -> None:
    """Serve stock RuView UI + sensing WS, fed from the LEX hub."""
    http_app = build_http_app(hub, lex_port=lex_port)
    ws_app = build_ws_app(hub, hz=hz)

    cfg_http = uvicorn.Config(
        http_app,
        host=bind_host,
        port=http_port,
        log_level="warning",
        access_log=False,
        loop="asyncio",
    )
    cfg_ws = uvicorn.Config(
        ws_app,
        host=bind_host,
        port=ws_port,
        log_level="warning",
        access_log=False,
        loop="asyncio",
    )
    srv_http = uvicorn.Server(cfg_http)
    srv_ws = uvicorn.Server(cfg_ws)
    # Nested under LEX uvicorn — don't steal SIGINT
    srv_http.install_signal_handlers = False
    srv_ws.install_signal_handlers = False

    log.info(
        "RuView UI http://%s:%d/  sensing ws://%s:%d/ws/sensing",
        bind_host,
        http_port,
        bind_host,
        ws_port,
    )
    await asyncio.gather(srv_http.serve(), srv_ws.serve())
