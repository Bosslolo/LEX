export type FloorId = string;

export interface Room {
  id: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface AccessPoint {
  id: string;
  label: string;
  floorId: FloorId;
  x: number;
  y: number;
  bssids: string[];
}

export interface Floor {
  id: FloorId;
  label: string;
  width: number;
  height: number;
  rooms: Room[];
}

export interface BuildingConfig {
  name: string;
  floors: Floor[];
  accessPoints: AccessPoint[];
}

export interface DeviceRule {
  mac?: string;
  label?: string;
  hostnamePattern?: string;
}

export interface PersonRule {
  id: string;
  displayName: string;
  devices?: DeviceRule[];
  radiusUser?: string;
  hostnamePatterns?: string[];
}

export interface PeopleConfig {
  people: PersonRule[];
}

/** Raw observation from DHCP, RADIUS, WiFi controller, ARP, etc. */
export interface ClientObservation {
  mac: string;
  hostname?: string;
  radiusUser?: string;
  ip?: string;
  ssid?: string;
  apId?: string;
  bssid?: string;
  rssi?: number;
  vlan?: string;
  vendor?: string;
  deviceKind?: "phone" | "laptop" | "tablet" | "watch" | "unknown";
  lastSeen: string;
}

export interface ResolvedDevice {
  mac: string;
  label: string;
  hostname?: string;
  rssi?: number;
  apId?: string;
}

export interface PersonLocation {
  personId: string;
  displayName: string;
  floorId: FloorId;
  x: number;
  y: number;
  confidence: number;
  method: "ap-zone" | "rssi-centroid" | "last-known";
  devices: ResolvedDevice[];
  primaryAp?: string;
  updatedAt: string;
}

export interface LocatorSnapshot {
  building: BuildingConfig;
  floorId: FloorId;
  people: PersonLocation[];
  unassigned: ClientObservation[];
  polledAt: string;
  source: string;
}
