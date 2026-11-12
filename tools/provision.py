#!/usr/bin/env python3
"""Provision LEX ESP32 boards over USB serial (Arduino Preferences namespace 'lex').

Usage:
  python tools/provision.py --port COM7 --role tx --ssid SchoolWiFi --password secret --collector 192.168.1.20
  python tools/provision.py --port COM5 --role rx --ssid SchoolWiFi --password secret --collector 192.168.1.20

The firmware must be running the LEX sketch. This sends a one-shot JSON line:
  {"cmd":"provision","ssid":"...","pass":"...","collector":"...","port":5005,"node":"tx1"}

If your flashed build does not yet include the serial provision hook, re-flash after
pulling latest firmware, or set values in source defaults before build.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("Install pyserial: pip install pyserial", file=sys.stderr)
    sys.exit(1)


PROVISION_SNIPPET = r'''
// Add to setup() after Serial.begin:
// handleSerialProvision();
void handleSerialProvision() {
  uint32_t start = millis();
  String line;
  while (millis() - start < 8000) {
    while (Serial.available()) {
      char c = Serial.read();
      if (c == '\n') {
        StaticJsonDocument<512> doc;
        if (deserializeJson(doc, line) == DeserializationError::Ok) {
          if (doc["cmd"] == "provision") {
            Preferences p; p.begin("lex", false);
            if (doc["ssid"]) p.putString("ssid", (const char*)doc["ssid"]);
            if (doc["pass"]) p.putString("pass", (const char*)doc["pass"]);
            if (doc["collector"]) p.putString("collector", (const char*)doc["collector"]);
            if (doc["port"]) p.putUShort("port", (uint16_t)doc["port"]);
            if (doc["node"]) p.putString("node", (const char*)doc["node"]);
            p.end();
            Serial.println("{\"ok\":true,\"provisioned\":true}");
            return;
          }
        }
        line = "";
      } else {
        line += c;
      }
    }
    delay(10);
  }
}
'''


def list_serial() -> None:
    print("Available ports:")
    for p in list_ports.comports():
        print(f"  {p.device:8}  {p.description}  [{p.hwid}]")


def main() -> int:
    ap = argparse.ArgumentParser(description="Provision LEX ESP32 WiFi + collector settings")
    ap.add_argument("--port", help="Serial port, e.g. COM7")
    ap.add_argument("--list", action="store_true", help="List serial ports")
    ap.add_argument("--role", choices=["tx", "rx"], default="tx")
    ap.add_argument("--ssid", required=False)
    ap.add_argument("--password", required=False)
    ap.add_argument("--collector", required=False, help="Laptop IP running the host")
    ap.add_argument("--collector-port", type=int, default=5005)
    ap.add_argument("--node", default=None)
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    if args.list or not args.port:
        list_serial()
        if not args.port:
            return 0

    if not args.ssid or args.password is None or not args.collector:
        print("Need --ssid --password --collector (and --port)", file=sys.stderr)
        return 2

    node = args.node or ("tx1" if args.role == "tx" else "rx1")
    payload = {
        "cmd": "provision",
        "ssid": args.ssid,
        "pass": args.password,
        "collector": args.collector,
        "port": args.collector_port,
        "node": node,
        "role": args.role,
    }

    ser = serial.Serial(args.port, args.baud, timeout=1)
    time.sleep(1.5)
    ser.reset_input_buffer()
    line = json.dumps(payload) + "\n"
    ser.write(line.encode("utf-8"))
    ser.flush()
    print(f"Sent provision to {args.port}: ssid={args.ssid} collector={args.collector} node={node}")

    deadline = time.time() + 5
    while time.time() < deadline:
        resp = ser.readline().decode("utf-8", errors="ignore").strip()
        if resp:
            print("board:", resp)
            if "provisioned" in resp or '"ok":true' in resp.replace(" ", ""):
                ser.close()
                return 0
    ser.close()
    print(
        "No ACK — board may need the serial provision hook. "
        "Flash latest firmware or paste the hook from tools/provision.py docstring.",
        file=sys.stderr,
    )
    print(PROVISION_SNIPPET)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
