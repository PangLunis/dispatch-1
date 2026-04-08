/**
 * Shared quota display helpers used by both dashboard.tsx and quota.tsx.
 */

/** Color for quota bar based on utilization percentage */
export function quotaBarColor(util: number): string {
  if (util >= 80) return "#ef4444";
  if (util >= 50) return "#eab308";
  return "#22c55e";
}

/**
 * Format a reset time as a human-readable relative string.
 * Returns an object so callers can adjust prefix/display for special cases.
 */
export interface ResetTimeInfo {
  /** The display text */
  text: string;
  /** Whether the reset time refers to a valid future window */
  isFresh: boolean;
}

export function formatResetTimeInfo(resetsAt: string): ResetTimeInfo {
  const diffMs = new Date(resetsAt).getTime() - Date.now();
  if (diffMs <= 0) {
    const agoMs = Math.abs(diffMs);
    const agoMins = Math.floor(agoMs / 60_000);
    const agoHours = Math.floor(agoMs / 3_600_000);
    // Show how long ago the window expired so the user sees actual staleness
    let agoText: string;
    if (agoHours > 24) {
      const days = Math.floor(agoHours / 24);
      agoText = `${days}d ${agoHours % 24}h`;
    } else if (agoHours > 0) {
      agoText = `${agoHours}h ${agoMins % 60}m`;
    } else {
      agoText = `${agoMins}m`;
    }
    if (agoHours > 24) return { text: `Stale (expired ${agoText} ago)`, isFresh: false };
    return { text: `Window expired ${agoText} ago`, isFresh: false };
  }
  const hours = Math.floor(diffMs / 3_600_000);
  const mins = Math.floor((diffMs % 3_600_000) / 60_000);
  let text: string;
  if (hours > 24) text = `${Math.floor(hours / 24)}d ${hours % 24}h`;
  else if (hours > 0) text = `${hours}h ${mins}m`;
  else text = `${mins}m`;
  return { text, isFresh: true };
}

/** Legacy helper — returns just the string (used in sparkline x-axis etc.) */
export function formatResetTime(resetsAt: string): string {
  const info = formatResetTimeInfo(resetsAt);
  return info.text;
}

// ---------------------------------------------------------------------------
// Quota burn-rate prediction
// ---------------------------------------------------------------------------

export interface QuotaPrediction {
  status: "safe" | "danger" | "unknown";
  projectedAtReset: number;
  hitsQuotaInMinutes?: number;
  message: string;
}

// Only predict for main quotas — model-specific sub-quotas (Opus/Sonnet)
// have bursty usage patterns where linear projection isn't meaningful.
const PERIOD_HOURS: Record<string, number> = {
  "5-Hour": 5,
  "7-Day": 168,
};

/**
 * Compute a burn-rate projection for a quota bar.
 * Returns status indicator + human-readable message.
 */
export function computeQuotaPrediction(
  label: string,
  utilization: number,
  resetsAt: string,
): QuotaPrediction {
  const now = Date.now();
  const resetMs = new Date(resetsAt).getTime();
  const remainingMs = resetMs - now;

  // Already past reset
  if (remainingMs <= 0) {
    return { status: "unknown", projectedAtReset: utilization, message: "" };
  }

  const periodHours = PERIOD_HOURS[label];
  if (!periodHours) {
    return { status: "unknown", projectedAtReset: utilization, message: "" };
  }

  const periodMs = periodHours * 3_600_000;
  const periodStartMs = resetMs - periodMs;
  const elapsedMs = now - periodStartMs;

  // Too early in period (<15 min elapsed)
  if (elapsedMs < 15 * 60_000) {
    return { status: "unknown", projectedAtReset: utilization, message: "" };
  }

  // Near reset (<30 min left)
  if (remainingMs < 30 * 60_000) {
    return { status: "safe", projectedAtReset: utilization, message: "resets soon" };
  }

  // Basically no usage
  if (utilization < 1) {
    return { status: "safe", projectedAtReset: 0, message: "on pace" };
  }

  const elapsedHours = elapsedMs / 3_600_000;
  const remainingHours = remainingMs / 3_600_000;
  const burnRatePerHour = utilization / elapsedHours;
  const projected = utilization + burnRatePerHour * remainingHours;

  // Format the time-to-hit-100 string
  function formatHitsIn(hoursToHit: number): string {
    const mins = Math.round(hoursToHit * 60);
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h > 24) {
      const d = Math.floor(h / 24);
      return `~${d}d ${h % 24}h`;
    }
    return h > 0 ? `~${h}h ${m}m` : `~${m}m`;
  }

  // Only show a warning when projected to exceed quota
  if (projected > 100) {
    const hoursToHit = (100 - utilization) / burnRatePerHour;
    return {
      status: "danger",
      projectedAtReset: projected,
      hitsQuotaInMinutes: Math.round(hoursToHit * 60),
      message: `runs out in ${formatHitsIn(hoursToHit)}`,
    };
  }

  // Won't go over — no message needed
  return { status: "safe", projectedAtReset: projected, message: "" };
}

export function predictionIcon(status: QuotaPrediction["status"]): string {
  switch (status) {
    case "danger": return "🔴";
    default: return "";
  }
}

export function predictionColor(status: QuotaPrediction["status"]): string {
  switch (status) {
    case "danger": return "#ef4444";
    default: return "#52525b";
  }
}

/** Format ISO timestamp to short time string, with date context for multi-day ranges */
export function formatTimestamp(isoStr: string, rangeHours?: number): string {
  const d = new Date(isoStr);
  if (rangeHours && rangeHours > 24) {
    return d.toLocaleDateString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
  }
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
