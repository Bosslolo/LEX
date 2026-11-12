import json
import time
import urllib.request

print("Sit still 5s, then wave/walk between boards for 8s...")
for i in range(14):
    with urllib.request.urlopen("http://127.0.0.1:8080/api/state") as resp:
        d = json.load(resp)
    print(
        f"t={i:02d} motion={d['csi_motion']:.2f} presence={d['csi_presence']:.2f} "
        f"energy={d['csi_energy']:.3f} base={d['csi_baseline']:.3f} thr={d['csi_threshold']:.3f} "
        f"cal={d['csi_calibrated']}"
    )
    time.sleep(1)
