import fs from "node:fs";
import path from "node:path";
import type { ClientObservation } from "../../shared/types.js";
import type { ClientSource } from "./types.js";
import { guessDeviceKind, normalizeMac } from "./types.js";

/**
 * Reads client observations from data/clients.json.
 * Wire your WiFi controller export or a custom poller to this file.
 */
export class FileClientSource implements ClientSource {
  readonly name = "file";

  constructor(private filePath: string) {}

  async fetchClients(): Promise<ClientObservation[]> {
    if (!fs.existsSync(this.filePath)) return [];
    const raw = JSON.parse(fs.readFileSync(this.filePath, "utf-8")) as {
      clients?: ClientObservation[];
    };
    return (raw.clients ?? []).map((c) => ({
      ...c,
      mac: normalizeMac(c.mac),
      deviceKind: c.deviceKind ?? guessDeviceKind(c.hostname, c.vendor),
    }));
  }
}

export function createClientSource(dataDir: string): ClientSource {
  const mode = process.env.LOCATOR_SOURCE ?? "mock";
  if (mode === "file") {
    return new FileClientSource(path.join(dataDir, "clients.json"));
  }
  return new MockClientSource();
}

/** Demo clients that move between floors — replace with real feed later. */
class MockClientSource implements ClientSource {
  readonly name = "mock";
  private tick = 0;

  async fetchClients(): Promise<ClientObservation[]> {
    this.tick += 1;
    const t = this.tick;
    const now = new Date().toISOString();

    const scenarios: ClientObservation[][] = [
      [
        {
          mac: "aa:bb:cc:dd:ee:01",
          hostname: "Demo-MacBook-Pro",
          radiusUser: "demo.user",
          ip: "192.168.1.100",
          ssid: "SCHOOL-WIFI",
          apId: "ap-demo-1",
          rssi: -58,
          vlan: "22",
          vendor: "Apple",
          deviceKind: "laptop",
          lastSeen: now,
        },
        {
          mac: "a6:99:d5:d9:d5:a8",
          hostname: "Demo-iPhone",
          radiusUser: "demo.user",
          ip: "192.168.1.101",
          ssid: "SCHOOL-WIFI",
          apId: "ap-demo-1",
          rssi: -62,
          vlan: "22",
          vendor: "Apple",
          deviceKind: "phone",
          lastSeen: now,
        },
        {
          mac: "58:38:79:7b:dd:87",
          hostname: "Tims-MacBook-Air",
          radiusUser: "student.a",
          ip: "192.168.1.102",
          ssid: "wlan-students",
          apId: "ap-eg-aula",
          rssi: -55,
          deviceKind: "laptop",
          lastSeen: now,
        },
        {
          mac: "30:5:5c:20:13:6a",
          hostname: "iPhone-von-Tim",
          radiusUser: "student.a",
          ip: "192.168.1.103",
          ssid: "wlan-students",
          apId: "ap-eg-aula",
          rssi: -59,
          deviceKind: "phone",
          lastSeen: now,
        },
      ],
      [
        {
          mac: "aa:bb:cc:dd:ee:01",
          hostname: "Demo-MacBook-Pro",
          radiusUser: "demo.user",
          ssid: "SCHOOL-WIFI",
          apId: "ap-1g-north",
          rssi: -61,
          deviceKind: "laptop",
          lastSeen: now,
        },
        {
          mac: "a6:99:d5:d9:d5:a8",
          hostname: "Demo-iPhone",
          radiusUser: "demo.user",
          ssid: "SCHOOL-WIFI",
          apId: "ap-1g-north",
          rssi: -64,
          deviceKind: "phone",
          lastSeen: now,
        },
        {
          mac: "3c:2a:f4:8d:0c:91",
          hostname: "Saras-iPad",
          radiusUser: "student.b",
          ssid: "wlan-students-SEKII",
          apId: "ap-1g-south",
          rssi: -57,
          deviceKind: "tablet",
          lastSeen: now,
        },
        {
          mac: "ee:e7:5c:30:e7:a9",
          hostname: "Saras-iPhone",
          radiusUser: "student.b",
          ssid: "wlan-students-SEKII",
          apId: "ap-1g-south",
          rssi: -60,
          deviceKind: "phone",
          lastSeen: now,
        },
      ],
      [
        {
          mac: "aa:bb:cc:dd:ee:01",
          hostname: "Demo-MacBook-Pro",
          radiusUser: "demo.user",
          ssid: "SCHOOL-WIFI",
          apId: "ap-eg-gym",
          rssi: -54,
          deviceKind: "laptop",
          lastSeen: now,
        },
        {
          mac: "a6:99:d5:d9:d5:a8",
          hostname: "Demo-iPhone",
          radiusUser: "demo.user",
          ssid: "SCHOOL-WIFI",
          apId: "ap-eg-mensa",
          rssi: -68,
          deviceKind: "phone",
          lastSeen: now,
        },
      ],
    ];

    return scenarios[t % scenarios.length]!;
  }
}
