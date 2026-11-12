"""UDP + USB-serial commands to ESP32 boards (calibrate blink, near-side pulse)."""

from __future__ import annotations

import asyncio
import json
import socket
import time
from typing import Any


TX_CMD_PORT = 4210
RX_CMD_PORT = 4211


def _detect_esp_serials() -> tuple[str | None, str | None]:
    """Best-effort TX/RX USB serial ports (Windows COM* or macOS cu.usbmodem*)."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return None, None
    found: list[str] = []
    for p in list_ports.comports():
        hwid = (p.hwid or "").upper()
        desc = (p.description or "").upper()
        name = p.device
        # Espressif USB-Serial/JTAG (VID 303A). Avoid generic "USB Serial" printers.
        if "303A" in hwid or "USB JTAG" in desc:
            found.append(name)
        elif "USBMODEM" in name.upper() or "SLAB_USBtoUART" in name.upper():
            found.append(name)
    # Stable order: prefer classic Windows mapping when present
    tx = next((p for p in found if p.upper() == "COM7"), found[0] if found else None)
    rest = [p for p in found if p != tx]
    rx = next((p for p in rest if p.upper() == "COM5"), rest[0] if rest else None)
    return tx, rx


_detected = _detect_esp_serials()
DEFAULT_TX_SERIAL = _detected[0]
DEFAULT_RX_SERIAL = _detected[1]


def _send(ip: str, port: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(raw, (ip, port))
    finally:
        sock.close()


def _send_serial(port: str | None, payload: dict[str, Any]) -> bool:
    """Send JSON command over USB serial (works when school WiFi blocks peer UDP)."""
    if not port:
        return False
    try:
        import serial
    except ImportError:
        return False
    ser = None
    try:
        # Avoid DTR/RTS toggle — on ESP32-S3 USB-JTAG that reboots the board.
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = 115200
        ser.timeout = 0.3
        ser.dtr = False
        ser.rts = False
        ser.open()
        time.sleep(0.05)
        ser.reset_input_buffer()
        ser.write((json.dumps(payload) + "\n").encode("utf-8"))
        ser.flush()
        time.sleep(0.05)
        return True
    except Exception:
        return False
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


async def notify_calibrate(
    *,
    tx_ip: str | None,
    rx_ip: str | None,
    seconds: float = 20.0,
    tx_serial: str | None = DEFAULT_TX_SERIAL,
    rx_serial: str | None = DEFAULT_RX_SERIAL,
) -> dict[str, bool]:
    """Blink identity LEDs on both boards during host calibration."""
    payload = {"cmd": "calibrate", "seconds": float(seconds)}
    sent = {"tx": False, "rx": False, "tx_serial": False, "rx_serial": False}

    def _go() -> None:
        if tx_ip:
            _send(tx_ip, TX_CMD_PORT, payload)
            sent["tx"] = True
        if rx_ip:
            _send(rx_ip, RX_CMD_PORT, payload)
            sent["rx"] = True
        sent["tx_serial"] = _send_serial(tx_serial, payload)
        sent["rx_serial"] = _send_serial(rx_serial, payload)

    await asyncio.to_thread(_go)
    return sent


async def notify_near(
    *,
    tx_ip: str | None,
    rx_ip: str | None,
    side: str,
    strength: float,
    tx_serial: str | None = DEFAULT_TX_SERIAL,
    rx_serial: str | None = DEFAULT_RX_SERIAL,
) -> None:
    """Tell boards which end of the beam has activity (for LED pulse)."""
    payload = {"cmd": "near", "side": side, "strength": float(strength)}

    def _go() -> None:
        if tx_ip:
            _send(tx_ip, TX_CMD_PORT, payload)
        if rx_ip:
            _send(rx_ip, RX_CMD_PORT, payload)
        # Serial near-pulses only if USB still plugged (optional)
        _send_serial(tx_serial, payload)
        _send_serial(rx_serial, payload)

    await asyncio.to_thread(_go)
