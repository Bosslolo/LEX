#!/usr/bin/env node
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = Number(process.env.PORT || 3847);
const ROOT = path.join(__dirname, "..", "web");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

/** In-memory demo state — replace with real sensor feed later. */
const state = {
  room: "LEX Lab",
  presence: false,
  confidence: 0.12,
  motion: 0.05,
  updatedAt: new Date().toISOString(),
  mode: "sim",
};

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function sendJson(res, code, data) {
  const body = JSON.stringify(data, null, 2);
  res.writeHead(code, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function serveStatic(req, res) {
  let urlPath = decodeURIComponent(req.url.split("?")[0]);
  if (urlPath === "/") urlPath = "/index.html";
  const filePath = path.normalize(path.join(ROOT, urlPath));
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    return res.end("Forbidden");
  }
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      return res.end("Not found");
    }
    const ext = path.extname(filePath);
    res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
    res.end(data);
  });
}

const server = http.createServer(async (req, res) => {
  const url = req.url.split("?")[0];

  if (req.method === "GET" && url === "/api/health") {
    return sendJson(res, 200, {
      ok: true,
      project: "LEX",
      port: PORT,
      time: new Date().toISOString(),
    });
  }

  if (req.method === "GET" && url === "/api/status") {
    return sendJson(res, 200, state);
  }

  if (req.method === "POST" && url === "/api/status") {
    try {
      const raw = await readBody(req);
      const patch = raw ? JSON.parse(raw) : {};
      if (typeof patch.presence === "boolean") state.presence = patch.presence;
      if (typeof patch.confidence === "number") state.confidence = patch.confidence;
      if (typeof patch.motion === "number") state.motion = patch.motion;
      if (typeof patch.room === "string") state.room = patch.room;
      if (typeof patch.mode === "string") state.mode = patch.mode;
      state.updatedAt = new Date().toISOString();
      return sendJson(res, 200, state);
    } catch {
      return sendJson(res, 400, { error: "invalid JSON" });
    }
  }

  if (req.method === "GET") return serveStatic(req, res);

  res.writeHead(405);
  res.end("Method not allowed");
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`LEX listening on http://127.0.0.1:${PORT}`);
  console.log("Cheap-first mode: software sim only (no ESP32 required yet)");
});
