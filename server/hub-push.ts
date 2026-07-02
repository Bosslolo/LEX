/**
 * Push metrics to the Laurin IT Check hub (outbound — works through school NAT).
 *
 * Env:
 *   HUB_PUSH_URL              comma-separated ingest URLs, e.g. https://hub.example.com/api/ingest/csh-floor-locator
 *   HUB_API_KEY               same key as on the hub server
 *   HUB_PUSH_ENABLED          set to "false"/"0" to disable (default: enabled)
 *   HUB_PUSH_INTERVAL_SECONDS push interval, default 60
 */
export function startHubPush(
  buildSnapshot: () => Promise<Record<string, unknown>> | Record<string, unknown>,
  appName = "csh-floor-locator"
): void {
  const enabled = (process.env.HUB_PUSH_ENABLED ?? "true").toLowerCase();
  if (enabled === "false" || enabled === "0") {
    console.log(`[hub-push] ${appName}: disabled via HUB_PUSH_ENABLED`);
    return;
  }

  const urls = (process.env.HUB_PUSH_URL ?? "")
    .split(",")
    .map((u) => u.trim())
    .filter(Boolean);
  const apiKey = process.env.HUB_API_KEY?.trim() ?? "";
  if (urls.length === 0 || !apiKey) {
    console.log(`[hub-push] ${appName}: skipped — set HUB_PUSH_URL and HUB_API_KEY`);
    return;
  }

  const intervalMs = Math.max(15, Number(process.env.HUB_PUSH_INTERVAL_SECONDS ?? 60)) * 1000;

  const push = async () => {
    let payload: Record<string, unknown>;
    try {
      payload = await buildSnapshot();
    } catch (err) {
      console.warn(`[hub-push] ${appName}: snapshot build failed:`, err);
      return;
    }
    for (const url of urls) {
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify(payload),
          signal: AbortSignal.timeout(15_000),
        });
        if (!res.ok) {
          console.warn(`[hub-push] ${appName}: HTTP ${res.status} → ${url}`);
        }
      } catch (err) {
        console.warn(
          `[hub-push] ${appName}: failed → ${url}:`,
          err instanceof Error ? err.message : err
        );
      }
    }
  };

  void push();
  const timer = setInterval(() => void push(), intervalMs);
  timer.unref?.();
  console.log(`[hub-push] ${appName}: pushing every ${intervalMs / 1000}s → ${urls.join(", ")}`);
}
