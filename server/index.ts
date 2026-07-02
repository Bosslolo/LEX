import express from "express";
import { timingSafeEqual } from "node:crypto";
import fs from "node:fs";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";
import type { BuildingConfig, LocatorSnapshot, PeopleConfig } from "../shared/types.js";
import { startHubPush } from "./hub-push.js";
import { buildSnapshot } from "./locator.js";
import { createClientSource } from "./sources/index.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");
const dataDir = path.join(projectRoot, "data");

function loadJson<T>(file: string): T {
  return JSON.parse(fs.readFileSync(path.join(dataDir, file), "utf-8")) as T;
}

const building = loadJson<BuildingConfig>("building.json");
const peopleConfig = loadJson<PeopleConfig>("people.json");
const source = createClientSource(dataDir);

async function buildHubSnapshotPayload(): Promise<Record<string, unknown>> {
  const problems: string[] = [];
  let clientsTotal = 0;
  let peopleTracked = 0;
  let unassignedCount = 0;
  try {
    const clients = await source.fetchClients();
    clientsTotal = clients.length;
    const floorId = building.floors[0]!.id;
    const { people, unassigned } = buildSnapshot(building, peopleConfig, clients, floorId);
    peopleTracked = people.length;
    unassignedCount = unassigned.length;
  } catch (e) {
    problems.push(`Client-Quelle nicht lesbar: ${String(e)}`);
  }
  return {
    app: "csh-floor-locator",
    generatedAt: new Date().toISOString(),
    source: source.name,
    clients: { total: clientsTotal },
    people: { tracked: peopleTracked, unassigned: unassignedCount },
    floors: { total: building.floors.length },
    problems,
  };
}

function hubAuthorized(req: express.Request): boolean {
  const expected = process.env.HUB_API_KEY?.trim() ?? "";
  if (!expected) return false;
  const auth = req.headers.authorization ?? "";
  if (!auth.startsWith("Bearer ")) return false;
  const token = auth.slice(7).trim();
  if (token.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(token), Buffer.from(expected));
}

async function startServer() {
  const app = express();
  const server = createServer(app);

  app.get("/api/health", (_req, res) => {
    res.json({ ok: true, source: source.name });
  });

  app.get("/api/hub/snapshot", async (req, res) => {
    if (!hubAuthorized(req)) {
      return res.status(401).json({ error: "Unauthorized" });
    }
    res.json(await buildHubSnapshotPayload());
  });

  app.get("/api/building", (_req, res) => {
    res.json(building);
  });

  app.get("/api/people", (_req, res) => {
    res.json(peopleConfig);
  });

  app.get("/api/locate", async (req, res) => {
    try {
      const floorId = typeof req.query.floor === "string" ? req.query.floor : building.floors[0]!.id;
      const clients = await source.fetchClients();
      const { people, unassigned } = buildSnapshot(building, peopleConfig, clients, floorId);

      const snapshot: LocatorSnapshot = {
        building,
        floorId,
        people,
        unassigned,
        polledAt: new Date().toISOString(),
        source: source.name,
      };
      res.json(snapshot);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  app.use(express.static(staticPath));
  app.get("*", (_req, res) => {
    res.sendFile(path.join(staticPath, "index.html"));
  });

  const port = process.env.PORT || 5190;
  server.listen(port, () => {
    console.log(`CSH Floor Locator → http://localhost:${port}/`);
    console.log(`  source: ${source.name} (set LOCATOR_SOURCE=file for data/clients.json)`);
    startHubPush(buildHubSnapshotPayload, "csh-floor-locator");
  });
}

startServer().catch(console.error);
