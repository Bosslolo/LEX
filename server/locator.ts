import type {
  AccessPoint,
  BuildingConfig,
  ClientObservation,
  PeopleConfig,
  PersonLocation,
  PersonRule,
  ResolvedDevice,
} from "../shared/types.js";
import { normalizeMac } from "./sources/types.js";
import { offsetFromRssi, rssiToWeight } from "./positioning/rssi-weight.js";

function globMatch(pattern: string, value: string): boolean {
  const re = new RegExp(
    "^" + pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$",
    "i",
  );
  return re.test(value);
}

function deviceLabel(obs: ClientObservation, rule?: PersonRule, index?: number): string {
  const fromRule = rule?.devices?.find((d) => d.mac && normalizeMac(d.mac) === obs.mac)?.label;
  if (fromRule) return fromRule;
  if (obs.deviceKind === "phone") return "Telefon";
  if (obs.deviceKind === "laptop") return "Laptop";
  if (obs.deviceKind === "tablet") return "Tablet";
  if (obs.hostname) return obs.hostname;
  return `Gerät ${(index ?? 0) + 1}`;
}

export function resolvePersonForClient(
  obs: ClientObservation,
  people: PersonRule[],
): PersonRule | undefined {
  const mac = normalizeMac(obs.mac);
  for (const person of people) {
    if (person.radiusUser && obs.radiusUser && person.radiusUser === obs.radiusUser) {
      return person;
    }
    if (person.devices?.some((d) => d.mac && normalizeMac(d.mac) === mac)) {
      return person;
    }
    if (obs.hostname && person.hostnamePatterns?.some((p) => globMatch(p, obs.hostname!))) {
      return person;
    }
  }
  return undefined;
}

/** Group observations by person id (or orphan mac). */
export function groupByPerson(
  clients: ClientObservation[],
  people: PersonRule[],
): Map<string, { person?: PersonRule; observations: ClientObservation[] }> {
  const groups = new Map<string, { person?: PersonRule; observations: ClientObservation[] }>();

  for (const obs of clients) {
    const person = resolvePersonForClient(obs, people);
    const key = person?.id ?? `mac:${normalizeMac(obs.mac)}`;
    const entry = groups.get(key) ?? { person, observations: [] };
    entry.observations.push(obs);
    groups.set(key, entry);
  }

  return groups;
}

export function locatePerson(
  personId: string,
  displayName: string,
  observations: ClientObservation[],
  building: BuildingConfig,
  personRule?: PersonRule,
): PersonLocation | null {
  if (observations.length === 0) return null;

  const apById = new Map(building.accessPoints.map((ap) => [ap.id, ap]));
  const apByBssid = new Map(
    building.accessPoints.flatMap((ap) => ap.bssids.map((b) => [normalizeMac(b), ap] as const)),
  );

  type Weighted = { ap: AccessPoint; weight: number; obs: ClientObservation };
  const weighted: Weighted[] = [];

  for (const obs of observations) {
    let ap: AccessPoint | undefined;
    if (obs.apId) ap = apById.get(obs.apId);
    if (!ap && obs.bssid) ap = apByBssid.get(normalizeMac(obs.bssid));
    if (!ap) continue;
    const rssi = obs.rssi ?? -65;
    weighted.push({ ap, weight: rssiToWeight(rssi), obs });
  }

  const now = new Date().toISOString();

  if (weighted.length === 0) {
    return null;
  }

  const floorVotes = new Map<string, number>();
  for (const w of weighted) {
    floorVotes.set(w.ap.floorId, (floorVotes.get(w.ap.floorId) ?? 0) + w.weight);
  }
  const floorId = [...floorVotes.entries()].sort((a, b) => b[1] - a[1])[0]![0];

  const onFloor = weighted.filter((w) => w.ap.floorId === floorId);
  const totalW = onFloor.reduce((s, w) => s + w.weight, 0);

  let x: number;
  let y: number;
  let method: PersonLocation["method"];
  let confidence: number;

  if (onFloor.length === 1) {
    const { ap, obs, weight } = onFloor[0]!;
    const off = offsetFromRssi(ap, obs.rssi ?? -65, personId);
    x = off.x;
    y = off.y;
    method = "ap-zone";
    confidence = Math.min(0.85, 0.45 + weight / 10);
  } else {
    x = onFloor.reduce((s, w) => s + w.ap.x * w.weight, 0) / totalW;
    y = onFloor.reduce((s, w) => s + w.ap.y * w.weight, 0) / totalW;
    method = "rssi-centroid";
    const spread = new Set(onFloor.map((w) => w.ap.id)).size;
    confidence = Math.min(0.92, 0.5 + spread * 0.12 + onFloor.length * 0.05);
  }

  const primaryAp = onFloor.sort((a, b) => b.weight - a.weight)[0]!.ap.id;

  const devices: ResolvedDevice[] = observations.map((obs, i) => ({
    mac: normalizeMac(obs.mac),
    label: deviceLabel(obs, personRule, i),
    hostname: obs.hostname,
    rssi: obs.rssi,
    apId: obs.apId,
  }));

  return {
    personId,
    displayName,
    floorId,
    x,
    y,
    confidence,
    method,
    devices,
    primaryAp,
    updatedAt: now,
  };
}

export function buildSnapshot(
  building: BuildingConfig,
  peopleConfig: PeopleConfig,
  clients: ClientObservation[],
  floorFilter?: string,
): { people: PersonLocation[]; unassigned: ClientObservation[] } {
  const groups = groupByPerson(clients, peopleConfig.people);
  const people: PersonLocation[] = [];
  const unassigned: ClientObservation[] = [];

  for (const [key, { person, observations }] of groups) {
    if (!person) {
      unassigned.push(...observations);
      continue;
    }
    const loc = locatePerson(person.id, person.displayName, observations, building, person);
    if (!loc) {
      unassigned.push(...observations);
      continue;
    }
    if (!floorFilter || loc.floorId === floorFilter) {
      people.push(loc);
    }
  }

  return { people, unassigned };
}
