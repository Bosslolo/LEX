"use strict";

async function refresh() {
  try {
    const res = await fetch("/api/status", { cache: "no-store" });
    if (!res.ok) throw new Error("status " + res.status);
    const s = await res.json();
    document.getElementById("room").textContent = s.room || "—";
    const el = document.getElementById("presence");
    el.textContent = s.presence ? "Someone in the room" : "Room empty";
    el.dataset.on = String(Boolean(s.presence));
    document.getElementById("confidence").textContent =
      typeof s.confidence === "number" ? (s.confidence * 100).toFixed(0) + "%" : "—";
    document.getElementById("motion").textContent =
      typeof s.motion === "number" ? s.motion.toFixed(2) : "—";
    document.getElementById("mode").textContent = s.mode || "—";
    document.getElementById("updated").textContent = s.updatedAt
      ? new Date(s.updatedAt).toLocaleTimeString()
      : "—";
  } catch (err) {
    document.getElementById("presence").textContent = "Server offline";
    document.getElementById("presence").dataset.on = "false";
    console.warn(err);
  }
}

refresh();
setInterval(refresh, 1000);
