import { useCallback, useEffect, useState } from "react";
import type { BuildingConfig, LocatorSnapshot } from "@shared/types";
import { FloorMap } from "./components/FloorMap";

const POLL_MS = 4000;

export default function App() {
  const [building, setBuilding] = useState<BuildingConfig | null>(null);
  const [floorId, setFloorId] = useState<string>("ground");
  const [snapshot, setSnapshot] = useState<LocatorSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/building")
      .then((r) => r.json())
      .then((b: BuildingConfig) => {
        setBuilding(b);
        setFloorId(b.floors[0]?.id ?? "ground");
      })
      .catch((e) => setError(String(e)));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`/api/locate?floor=${encodeURIComponent(floorId)}`);
      if (!res.ok) throw new Error(await res.text());
      setSnapshot(await res.json());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [floorId]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const floor = building?.floors.find((f) => f.id === floorId);
  const aps = building?.accessPoints.filter((ap) => ap.floorId === floorId) ?? [];

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>CSH Floor Locator</h1>
          <p className="muted">
            Geräte → Personen → Position auf dem Grundriss
            {snapshot && (
              <>
                {" "}
                · Quelle: <code>{snapshot.source}</code> · {new Date(snapshot.polledAt).toLocaleTimeString("de-CH")}
              </>
            )}
          </p>
        </div>
        <div className="floor-tabs" role="tablist">
          {building?.floors.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={f.id === floorId}
              className={f.id === floorId ? "tab active" : "tab"}
              onClick={() => setFloorId(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      <main className="layout">
        <section className="map-panel">
          {floor && snapshot ? (
            <FloorMap floor={floor} accessPoints={aps} people={snapshot.people} />
          ) : (
            <div className="loading">Lade Grundriss…</div>
          )}
        </section>

        <aside className="sidebar">
          <h2>Auf {floor?.label ?? "…"}</h2>
          {snapshot?.people.length === 0 && <p className="muted">Keine zugeordneten Personen auf dieser Etage.</p>}
          <ul className="person-list">
            {snapshot?.people.map((p) => (
              <li key={p.personId} className="person-card">
                <div className="person-name">{p.displayName}</div>
                <div className="person-meta">
                  {Math.round(p.confidence * 100)}% · {p.method === "rssi-centroid" ? "Mehr-AP" : "AP-Zone"}
                  {p.primaryAp && ` · ${p.primaryAp}`}
                </div>
                <ul className="device-list">
                  {p.devices.map((d) => (
                    <li key={d.mac}>
                      <span>{d.label}</span>
                      {d.rssi != null && <span className="rssi">{d.rssi} dBm</span>}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>

          {snapshot && snapshot.unassigned.length > 0 && (
            <>
              <h3 className="sidebar-sub">Nicht zugeordnet</h3>
              <ul className="unassigned">
                {snapshot.unassigned.map((c) => (
                  <li key={c.mac}>
                    <code>{c.mac}</code>
                    {c.hostname && ` · ${c.hostname}`}
                  </li>
                ))}
              </ul>
            </>
          )}
        </aside>
      </main>
    </div>
  );
}
