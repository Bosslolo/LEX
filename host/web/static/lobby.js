const statusEl = document.getElementById("status");
const hintUrl = document.getElementById("hintUrl");
hintUrl.textContent = `${location.origin}/`;

async function getMode() {
  const res = await fetch("/api/mode");
  const data = await res.json();
  statusEl.textContent = `mode: ${data.mode} · boards udp tx=${data.sent?.tx} rx=${data.sent?.rx}`;
  return data;
}

async function setMode(mode, { go } = {}) {
  statusEl.textContent = `switching → ${mode}…`;
  try {
    const res = await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    const data = await res.json();
    statusEl.textContent = `mode: ${data.mode} · udp tx=${!!data.sent?.tx} rx=${!!data.sent?.rx} · serial tx=${!!data.sent?.tx_serial} rx=${!!data.sent?.rx_serial}`;
    if (!go) return data;
    if (mode === "lex") location.href = "/lex";
    else if (mode === "ruview") location.href = "/ruview"; // server honours --ruview-http-port
    else location.href = "/";
    return data;
  } catch (err) {
    statusEl.textContent = `mode switch failed (${mode}) — is the host running?`;
    return { ok: false, error: String(err) };
  }
}

document.getElementById("btnLex").onclick = () => setMode("lex", { go: true });
document.getElementById("btnRuview").onclick = () => setMode("ruview", { go: true });
document.getElementById("btnLobby").onclick = () => setMode("lobby", { go: false });

getMode().catch(() => {
  statusEl.textContent = "mode: offline (is the school host running?)";
});
