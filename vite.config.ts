import react from "@vitejs/plugin-react";
import path from "node:path";
import fs from "node:fs";
import type { Plugin, ViteDevServer } from "vite";
import { defineConfig } from "vite";
import type { BuildingConfig, LocatorSnapshot, PeopleConfig } from "./shared/types";
import { buildSnapshot } from "./server/locator";
import { createClientSource } from "./server/sources/index";

const projectRoot = import.meta.dirname;
const dataDir = path.join(projectRoot, "data");

function loadJson<T>(file: string): T {
  return JSON.parse(fs.readFileSync(path.join(dataDir, file), "utf-8")) as T;
}

function locatorApiPlugin(): Plugin {
  const building = loadJson<BuildingConfig>("building.json");
  const peopleConfig = loadJson<PeopleConfig>("people.json");
  const source = createClientSource(dataDir);

  return {
    name: "csh-locator-api",
    configureServer(server: ViteDevServer) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url?.split("?")[0] ?? "";
        const send = (code: number, body: unknown) => {
          res.statusCode = code;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify(body));
        };

        if (url === "/api/health") {
          send(200, { ok: true, source: source.name });
          return;
        }
        if (url === "/api/building") {
          send(200, building);
          return;
        }
        if (url === "/api/people") {
          send(200, peopleConfig);
          return;
        }
        if (url === "/api/locate") {
          try {
            const q = new URL(req.url!, "http://localhost").searchParams;
            const floorId = q.get("floor") ?? building.floors[0]!.id;
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
            send(200, snapshot);
          } catch (e) {
            send(500, { error: String(e) });
          }
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), locatorApiPlugin()],
  resolve: {
    alias: {
      "@": path.resolve(projectRoot, "client", "src"),
      "@shared": path.resolve(projectRoot, "shared"),
    },
  },
  root: path.resolve(projectRoot, "client"),
  build: {
    outDir: path.resolve(projectRoot, "dist/public"),
    emptyOutDir: true,
  },
  server: {
    port: 5190,
    strictPort: true,
    host: true,
  },
});
