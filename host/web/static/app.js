import { RoomScene } from "./room3d.js?v=21";

const state = {
  data: null,
  layers: { csi: true, cam: false, phone: true },
};

const els = {
  modePill: document.getElementById("modePill"),
  scorecard: document.getElementById("scorecard"),
  phoneMeta: document.getElementById("phoneMeta"),
  phoneList: document.getElementById("phoneList"),
  panelPhone: document.getElementById("panelPhone"),
  drawer: document.getElementById("drawer"),
  statMotion: document.getElementById("statMotion"),
  statPresence: document.getElementById("statPresence"),
  statPps: document.getElementById("statPps"),
  statNear: document.getElementById("statNear"),
};

const room = new RoomScene(document.getElementById("room3d"));

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function nearLabel(side) {
  if (side === "tx") return `<span class="near-badge tx">Near TX</span>`;
  if (side === "rx") return `<span class="near-badge rx">Near RX</span>`;
  if (side === "mid") return `<span class="near-badge mid">Middle</span>`;
  return `<span class="near-badge none">Quiet</span>`;
}

function nearText(side) {
  if (side === "tx") return "TX";
  if (side === "rx") return "RX";
  if (side === "mid") return "mid";
  return "—";
}

/** Stable angle from MAC/name; RSSI → distance from room center (stronger = closer). */
function phoneMarkers(devices) {
  return (devices || []).map((d, i) => {
    const key = String(d.addr || d.name || i);
    let h = 2166136261;
    for (let c = 0; c < key.length; c++) {
      h ^= key.charCodeAt(c);
      h = Math.imul(h, 16777619);
    }
    const ang = ((h >>> 0) % 360) * (Math.PI / 180);
    const rssi = Number(d.rssi ?? -70);
    const closeness = Math.max(0, Math.min(1, (rssi + 95) / 55));
    // 9×7 room — keep markers inside ~3.5 m radius
    const r = 3.4 - closeness * 2.4;
    return {
      name: d.name || d.addr || `dev${i + 1}`,
      addr: d.addr || "",
      rssi,
      position: [Math.cos(ang) * r, 0, Math.sin(ang) * r],
      source: "phone",
    };
  });
}

function renderPhones(devices) {
  const list = devices || [];
  if (!list.length) {
    els.phoneList.innerHTML = `<div class="empty">No nearby BLE devices yet.</div>`;
    return;
  }
  els.phoneList.innerHTML = list
    .map((d) => {
      const bars = Math.max(1, Math.min(5, Math.round((d.rssi + 100) / 10)));
      return `<div class="dev">
        <div class="dev-name">${escapeHtml(d.name || d.addr)}</div>
        <div class="dev-meta">${escapeHtml(d.addr)} · ${d.rssi} dBm
          <span class="bars">${"▮".repeat(bars)}${"▯".repeat(5 - bars)}</span>
        </div>
      </div>`;
    })
    .join("");
}

function paintHud() {
  const d = state.data;
  els.panelPhone.classList.toggle("off", !state.layers.phone);
  if (!d) {
    els.modePill.textContent = "connecting";
    return;
  }
  const cal = d.csi_calibrating ? " · calibrating" : d.csi_calibrated ? "" : " · uncalibrated";
  els.modePill.textContent = `${d.mode || "live"}${cal}`;
  els.phoneMeta.textContent = `${d.ble_count || 0} devices`;
  els.statMotion.textContent = `${Math.round((d.csi_motion || 0) * 100)}%`;
  els.statPresence.textContent = d.csi_presence > 0.5 ? "YES" : "no";
  els.statPps.textContent = `${Number(d.csi_pps || 0).toFixed(0)}/s`;
  els.statNear.textContent = nearText(d.near_side || "none");

  els.scorecard.innerHTML = `
    <div class="chip csi"><label>Where (WiFi path)</label><strong>${nearLabel(d.near_side || "none")}</strong></div>
    <div class="chip phones"><label>Devices in room</label><strong>${d.ble_count || 0}</strong></div>
    <div class="chip"><label>Motion</label><strong>${Math.round((d.csi_motion || 0) * 100)}%</strong></div>
    <div class="chip"><label>Presence</label><strong>${d.csi_presence > 0.5 ? "yes" : "no"}</strong></div>
  `;

  if (state.layers.phone) renderPhones(d.devices || []);
  else els.phoneList.innerHTML = `<div class="empty">Devices layer off</div>`;

  // Radio / WiFi motion markers only — no camera people
  const mapped = (d.room_persons || []).filter((p) => p.source === "csi");

  room.setLayers(state.layers);
  room.update({
    ...d,
    room_persons: mapped,
    phone_markers: phoneMarkers(d.devices || []),
  });
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    state.data = JSON.parse(ev.data);
    paintHud();
  };
  ws.onclose = () => {
    state.data = null;
    if (els.modePill) els.modePill.textContent = "reconnecting";
    room.update({
      csi_motion: 0,
      csi_presence: 0,
      near_side: "none",
      room_persons: [],
      phone_markers: [],
      signal_field: { values: [] },
    });
    paintHud();
    setTimeout(connect, 1000);
  };
  ws.onerror = () => {
    try {
      ws.close();
    } catch (_) {
      /* ignore */
    }
  };
}

document.getElementById("togCsi").onchange = (e) => {
  state.layers.csi = e.target.checked;
  paintHud();
};
document.getElementById("togPhone").onchange = (e) => {
  state.layers.phone = e.target.checked;
  paintHud();
};
document.getElementById("togTop").onchange = (e) => room.setTopDown(e.target.checked);
document.getElementById("btnCalibrate").onclick = async () => {
  els.modePill.textContent = "calibrating";
  try {
    await fetch("/api/calibrate?seconds=20", { method: "POST" });
  } catch (_) {
    els.modePill.textContent = "calibrate failed";
  }
};
document.getElementById("btnPresent").onclick = () => document.body.classList.toggle("presenter");
document.getElementById("btnPanel").onclick = () => els.drawer.classList.toggle("open");
document.getElementById("btnLobby").onclick = async () => {
  try {
    await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "lobby" }),
    });
  } catch (_) {
    /* still leave the page */
  }
  location.href = "/";
};

connect();
