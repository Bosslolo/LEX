import json
import time
import urllib.request

for _ in range(5):
    with urllib.request.urlopen("http://127.0.0.1:8080/api/state") as resp:
        d = json.load(resp)
    devices = d.get("devices") or []
    names = ", ".join(f"{x.get('name')}({x.get('rssi')})" for x in devices[:5]) or "-"
    print(
        f"mode={d['mode']} boards={d['boards_ok']} pps={d['csi_pps']:.1f} "
        f"motion={d['csi_motion']:.2f} ble={d['ble_count']} "
        f"devices=[{names}]"
    )
    time.sleep(2)
