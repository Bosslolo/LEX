import { RoomScene } from "./room3d.js?v=16";

const state = {
  data: null,
  layers: { csi: true, cam: true, phone: true },
};

const els = {
  modePill: document.getElementById("modePill"),
  scorecard: document.getElementById("scorecard"),
  notes: document.getElementById("notes"),
  phoneMeta: document.getElementById("phoneMeta"),
  phoneList: document.getElementById("phoneList"),
  panelPhone: document.getElementById("panelPhone"),
  compareMeta: document.getElementById("compareMeta"),
  compareBox: document.getElementById("compareBox"),
  faceMeta: document.getElementById("faceMeta"),
  faceList: document.getElementById("faceList"),
  faceName: document.getElementById("faceName"),
  drawer: document.getElementById("drawer"),
  statMotion: document.getElementById("statMotion"),
  statPresence: document.getElementById("statPresence"),
  statPps: document.getElementById("statPps"),
  statCam: document.getElementById("statCam"),
};

const room = new RoomScene(document.getElementById("room3d"));

const isRuviewSkin = false; // RuView is the stock UI on :3000, not a LEX reskin
if (isRuviewSkin) {
  document.body.classList.add("ruview-skin");
  const h1 = document.querySelector("header.top h1");
  if (h1) h1.textContent = "RuView";
  document.title = "RuView · WiFi Sensing";
}

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
  return `<span class="near-badge none">No hit</span>`;
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
    const r = 5.6 - closeness * 4.0;
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

function renderFaces(gallery) {
  const list = gallery || [];
  els.faceMeta.textContent = `${list.length} enrolled`;
  if (!list.length) {
    els.faceList.innerHTML = `<div class="empty">No faces yet — type a name and enroll.</div>`;
    return;
  }
  els.faceList.innerHTML = list
    .map(
      (f) => `<div class="row">
        <span>${escapeHtml(f.name)}</span>
        <button data-del="${escapeHtml(f.name)}">Remove</button>
      </div>`
    )
    .join("");
  els.faceList.querySelectorAll("button[data-del]").forEach((btn) => {
    btn.onclick = async () => {
      await fetch(`/api/faces/${encodeURIComponent(btn.dataset.del)}`, { method: "DELETE" });
    };
  });
}

function renderCompare(c) {
  if (!c || !Object.keys(c).length) {
    els.compareBox.innerHTML = `<div class="empty">Waiting for camera + radio…</div>`;
    els.compareMeta.textContent = "";
    return;
  }
  els.compareMeta.textContent =
    c.presence_agreement_pct != null ? `${c.presence_agreement_pct}% vs camera` : "no camera ref";
  const rows = (c.rows || [])
    .map((r) => {
      const cls = r.vs_camera === "agree" ? "agree" : r.vs_camera === "disagree" ? "disagree" : "";
      return `<div class="row">
        <span>${escapeHtml(r.source)} · ${r.detects_someone ? "YES" : "no"}</span>
        <span class="${cls}">${escapeHtml(r.vs_camera)}</span>
      </div>`;
    })
    .join("");
  const faces = (c.named_faces || []).join(", ") || "—";
  els.compareBox.innerHTML = `
    <div class="headline">${escapeHtml(c.headline || "")}</div>
    ${rows}
    <div class="row"><span>Named faces</span><strong>${escapeHtml(faces)}</strong></div>
    <div class="row"><span>Counts cam/face/phone</span><strong>${c.camera_count}/${c.face_count}/${c.ble_count}</strong></div>
  `;
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
  els.statCam.textContent = d.camera_ok ? `${d.camera_count}` : "off";
  els.notes.textContent = (d.notes || []).slice(0, 2).join(" · ");

  els.scorecard.innerHTML = `
    <div class="chip csi"><label>Radio where</label><strong>${nearLabel(d.near_side || "none")}</strong></div>
    <div class="chip camera"><label>Faces</label><strong>${(d.named_faces || []).join(", ") || "—"}</strong></div>
    <div class="chip phones"><label>Devices in room</label><strong>${d.ble_count || 0}</strong></div>
    <div class="chip"><label>Agree vs cam</label><strong>${
      d.comparison?.presence_agreement_pct != null ? d.comparison.presence_agreement_pct + "%" : "—"
    }</strong></div>
  `;

  renderCompare(d.comparison || {});
  renderFaces(d.face_gallery || []);
  if (state.layers.phone) renderPhones(d.devices || []);
  else els.phoneList.innerHTML = `<div class="empty">Devices layer off</div>`;

  const mapped = [];
  for (const p of d.people || []) {
    mapped.push({
      id: p.id,
      source: p.source || (p.name ? "face" : "camera"),
      name: p.name || "",
      position: [(p.x - 0.5) * 14, 0, (p.y - 0.5) * 10],
      motion_score: (p.conf || 0.5) * 80,
    });
  }
  for (const p of d.room_persons || []) {
    if (p.source === "csi") mapped.push(p);
  }

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
  ws.onclose = () => setTimeout(connect, 1000);
}

document.getElementById("togCsi").onchange = (e) => {
  state.layers.csi = e.target.checked;
  paintHud();
};
document.getElementById("togCam").onchange = (e) => {
  state.layers.cam = e.target.checked;
  paintHud();
};
document.getElementById("togPhone").onchange = (e) => {
  state.layers.phone = e.target.checked;
  paintHud();
};
document.getElementById("togTop").onchange = (e) => room.setTopDown(e.target.checked);
document.getElementById("btnCalibrate").onclick = async () => {
  els.modePill.textContent = "calibrating";
  await fetch("/api/calibrate?seconds=20", { method: "POST" });
};
document.getElementById("btnPresent").onclick = () => document.body.classList.toggle("presenter");
document.getElementById("btnPanel").onclick = () => els.drawer.classList.toggle("open");
document.getElementById("btnLobby").onclick = async () => {
  await fetch("/api/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "lobby" }),
  });
  location.href = "/";
};
document.getElementById("btnEnroll").onclick = async () => {
  const name = els.faceName.value.trim();
  if (!name) return;
  const body = new FormData();
  body.append("name", name);
  const res = await fetch("/api/faces/enroll", { method: "POST", body });
  const data = await res.json();
  if (!data.ok) alert(data.error || "enroll failed");
  else els.faceName.value = "";
};

connect();
