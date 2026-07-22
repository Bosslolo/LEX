/**
 * RSSI → weight and AP offset helpers.
 * Future: room fingerprint matching ported from RuView (see integrations/ruview/).
 */

import type { AccessPoint } from "../../shared/types.js";

export function rssiToWeight(rssi: number): number {
  const clamped = Math.max(-90, Math.min(-40, rssi));
  return Math.pow(10, (clamped + 90) / 15);
}

export function offsetFromRssi(ap: AccessPoint, rssi: number, seed: string): { x: number; y: number } {
  const strength = (rssi + 90) / 50;
  const dist = (1 - Math.min(1, strength)) * 12;
  const hash = [...seed].reduce((a, c) => a + c.charCodeAt(0), 0);
  const angle = (hash % 360) * (Math.PI / 180);
  return {
    x: ap.x + Math.cos(angle) * dist,
    y: ap.y + Math.sin(angle) * dist,
  };
}

/** Minimum observations before trusting a location (future quality gate). */
export function observationQuality(observationCount: number, apSpread: number): number {
  if (observationCount === 0) return 0;
  return Math.min(1, 0.4 + apSpread * 0.15 + observationCount * 0.05);
}
