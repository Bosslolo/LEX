import { useCallback, useEffect, useMemo, useState } from "react";
import type { BuildingConfig, LocatorSnapshot } from "@shared/types";
import { FloorMap } from "./components/FloorMap";

const POLL_MS = 4000;
const STALE_MS = 20_000;

export default function App() {
  const [building, setBuilding] = useState<BuildingConfig | null>(null);
  const [floorId, setFloorId] = useState<string>("ground");
  const [snapshot, setSnapshot] = useState<LocatorSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    fetch("/api/building")
      .then((r) => {
        if (!r.ok) throw new Error(`Gebäude: HTTP ${r.status}`);
        return r.json();
      })
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
      setNow(Date.now());
    } catch (e) {
      setError(String(e));
    }
  }, [floorId]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const floor = building?.floors.find((f) => f.id === floorId);
  const aps = useMemo(
    () => building?.accessPoints.filter((ap) => ap.floorId === floorId) ?? [],
    [building, floorId]
  );

  const polledAgeMs = snapshot ? now - new Date(snapshot.polledAt).getTime() : null;
  const isStale = polledAgeMs != null && polledAgeMs > STALE_MS;
  const peopleOnFloor = snapshot?.people.length ?? 0;
  const unassigned = snapshot?.unassigned.length ?? 0;
  const ready = Boolean(floor && snapshot);

  return (
    <div className="app">
      <header className="header">
        <div className="brand-block">
          <p className="brand-kicker">
            <span className={`live-dot${isStale ? " is-stale" : ""}`} aria-hidden />
            CSH · Live
          </p>
          <h1>
            Floor <span>Locator</span>
          </h1>
          <p className="lede">
            Geräte werden Personen zugeordnet und auf dem Grundriss der Christlichen Schule
            Herzogenbuchsee gezeigt.
          </p>
          <div className="meta-row">
            <span className="chip">
              Quelle <code>{snapshot?.source ?? "…"}</code>
            </span>
            {snapshot && (
              <span className="chip">
                Update{" "}
                <strong>
                  {new Date(snapshot.polledAt).toLocaleTimeString("de-CH", {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </strong>
              </span>
            )}
            <span className="chip">
              Etage <strong>{floor?.label ?? "…"}</strong>
            </span>
          </div>
        </div>

        <div className="header-actions">
          <div className="floor-tabs" role="tablist" aria-label="Etage">
            {building?.floors.map((f) => (
              <button
                key={f.id}
                type="button"
                role="tab"
                aria-selected={f.id === floorId}
                className={f.id === floorId ? "tab active" : "tab"}
                onClick={() => setFloorId(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="stat-pills" aria-label="Kurzstatistik">
            <div className="stat-pill">
              <span>Personen</span>
              <strong>{peopleOnFloor}</strong>
            </div>
            <div className="stat-pill">
              <span>APs</span>
              <strong>{aps.length}</strong>
            </div>
            <div className="stat-pill">
              <span>Offen</span>
              <strong>{unassigned}</strong>
            </div>
          </div>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      <main className="layout">
        <section className="map-panel">
          {ready ? (
            <div className="map-stage" key={floorId}>
              <FloorMap floor={floor!} accessPoints={aps} people={snapshot!.people} />
              <div className="legend" aria-hidden>
                <span className="legend-item">
                  <span className="legend-swatch ap" /> Access Point
                </span>
                <span className="legend-item">
                  <span className="legend-swatch person" /> Person
                </span>
              </div>
            </div>
          ) : (
            <div className="loading">
              <div className="loading-spinner" aria-hidden />
              <div>Lade Grundriss…</div>
            </div>
          )}
        </section>

        <aside className="sidebar">
          <div className="sidebar-head">
            <h2>Auf {floor?.label ?? "…"}</h2>
            <span className="sidebar-count">
              {peopleOnFloor} {peopleOnFloor === 1 ? "Person" : "Personen"}
            </span>
          </div>

          {ready && peopleOnFloor === 0 ? (
            <div className="empty-state">
              <strong>Keine Personen auf dieser Etage</strong>
              <p>
                Sobald zugeordnete Geräte hier funken, erscheinen Pins auf dem Plan und in dieser
                Liste.
              </p>
            </div>
          ) : (
            <ul className="person-list">
              {snapshot?.people.map((p, index) => (
                <li
                  key={p.personId}
                  className="person-card"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <div className="person-name">{p.displayName}</div>
                  <div className="person-meta">
                    {Math.round(p.confidence * 100)}% ·{" "}
                    {p.method === "rssi-centroid" ? "Mehr-AP" : "AP-Zone"}
                    {p.primaryAp ? ` · ${p.primaryAp}` : ""}
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
          )}

          {snapshot && snapshot.unassigned.length > 0 && (
            <>
              <h3 className="sidebar-sub">Nicht zugeordnet</h3>
              <ul className="unassigned">
                {snapshot.unassigned.map((c) => (
                  <li key={c.mac}>
                    <code>{c.mac}</code>
                    {c.hostname ? ` · ${c.hostname}` : ""}
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
