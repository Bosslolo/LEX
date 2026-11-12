"""Run RuView HTTP (:3000) + sensing WebSocket (:3001) alongside LEX."""

from __future__ import annotations

import asyncio
import logging
import socket

import uvicorn

from host.collector.state import StateHub
from host.ruview_ui.http_app import build_http_app
from host.ruview_ui.ws_app import build_ws_app

log = logging.getLogger("lex.ruview_ui")


def _port_free(host: str, port: int) -> bool:
    bind_host = "0.0.0.0" if host in ("0.0.0.0", "", None) else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((bind_host if bind_host != "0.0.0.0" else "0.0.0.0", port))
        return True
    except OSError:
        return False


async def serve_ruview_ui(
    hub: StateHub,
    *,
    bind_host: str = "0.0.0.0",
    http_port: int = 3000,
    ws_port: int = 3001,
    lex_port: int = 8080,
    hz: float = 10.0,
) -> None:
    """Serve stock RuView UI + sensing WS, fed from the LEX hub.

    Bind failures must NOT kill the parent LEX process on :8080.
    """
    if http_port == ws_port or http_port == lex_port or ws_port == lex_port:
        log.error(
            "RuView ports collide (http=%s ws=%s lex=%s) — skipping RuView UI",
            http_port,
            ws_port,
            lex_port,
        )
        return
    if not _port_free(bind_host, http_port) or not _port_free(bind_host, ws_port):
        log.error(
            "RuView ports busy (:%s / :%s) — LEX continues without RuView UI. "
            "Stop the other process or pass --no-ruview-ui / different ports.",
            http_port,
            ws_port,
        )
        return

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
    # Nested under LEX uvicorn — don't steal SIGINT (best-effort on older uvicorn)
    srv_http.install_signal_handlers = False
    srv_ws.install_signal_handlers = False

    log.info(
        "RuView UI http://%s:%d/  sensing ws://%s:%d/ws/sensing",
        bind_host,
        http_port,
        bind_host,
        ws_port,
    )
    try:
        await asyncio.gather(srv_http.serve(), srv_ws.serve())
    except SystemExit as exc:
        log.error("RuView UI exited (%s) — LEX room UI on :%s keeps running", exc, lex_port)
    except OSError as exc:
        log.error("RuView UI bind failed (%s) — LEX continues", exc)
