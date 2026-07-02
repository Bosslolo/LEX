import type { ClientObservation } from "../../shared/types.js";

/** Pluggable source — swap for UniFi, Aruba, Sophos, DHCP export, etc. */
export interface ClientSource {
  readonly name: string;
  fetchClients(): Promise<ClientObservation[]>;
}

export function normalizeMac(mac: string): string {
  return mac.toLowerCase().replace(/[^a-f0-9]/g, "").replace(/(.{2})(?=.)/g, "$1:");
}

export function guessDeviceKind(hostname?: string, vendor?: string): ClientObservation["deviceKind"] {
  const h = (hostname ?? "").toLowerCase();
  const v = (vendor ?? "").toLowerCase();
  if (h.includes("iphone") || h.includes("android") || v.includes("apple") && h.includes("phone")) return "phone";
  if (h.includes("ipad") || h.includes("tablet")) return "tablet";
  if (h.includes("macbook") || h.includes("mac") || h.includes("laptop") || v.includes("apple")) return "laptop";
  if (h.includes("watch")) return "watch";
  return "unknown";
}
