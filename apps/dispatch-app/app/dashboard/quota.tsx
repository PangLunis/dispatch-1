import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack } from "expo-router";
import { getDashboardQuotaHistory } from "@/src/api/dashboard";
import type { QuotaHistoryResponse, QuotaSnapshot, QuotaHeavySession } from "@/src/api/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function quotaBarColor(util: number): string {
  if (util >= 80) return "#ef4444";
  if (util >= 50) return "#eab308";
  return "#22c55e";
}

function formatResetTime(resetsAt: string): string {
  const diffMs = new Date(resetsAt).getTime() - Date.now();
  if (diffMs <= 0) return "now";
  const hours = Math.floor(diffMs / 3_600_000);
  const mins = Math.floor((diffMs % 3_600_000) / 60_000);
  if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

function formatAge(isoStr: string): string {
  const diffMs = Date.now() - new Date(isoStr).getTime();
  if (diffMs < 0) return "just now";
  const secs = Math.floor(diffMs / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m ago`;
}

function formatTimestamp(isoStr: string): string {
  const d = new Date(isoStr);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// ---------------------------------------------------------------------------
// SparklineChart component
// ---------------------------------------------------------------------------

function SparklineChart({
  snapshots,
  field,
  label,
  height = 120,
}: {
  snapshots: QuotaSnapshot[];
  field: "five_hour" | "seven_day";
  label: string;
  height?: number;
}) {
  const [containerWidth, setContainerWidth] = useState(
    Dimensions.get("window").width - 48,
  );

  if (snapshots.length < 2) {
    return (
      <View style={sparkStyles.container}>
        <Text style={sparkStyles.label}>{label}</Text>
        <View style={[sparkStyles.chartArea, { height }]}>
          <Text style={sparkStyles.emptyText}>
            Collecting data — check back in ~15 min
          </Text>
        </View>
      </View>
    );
  }

  const barWidth = Math.max(3, Math.floor(containerWidth / snapshots.length) - 1);
  const gap = 1;

  // X-axis labels: first, middle, last
  const firstTs = formatTimestamp(snapshots[0].ts);
  const midTs = formatTimestamp(snapshots[Math.floor(snapshots.length / 2)].ts);
  const lastTs = formatTimestamp(snapshots[snapshots.length - 1].ts);

  return (
    <View style={sparkStyles.container}>
      <Text style={sparkStyles.label}>{label}</Text>
      <View
        style={[sparkStyles.chartArea, { height }]}
        onLayout={(e) => setContainerWidth(e.nativeEvent.layout.width)}
      >
        <View style={sparkStyles.barsRow}>
          {snapshots.map((snap, i) => {
            const val = snap[field] ?? 0;
            const barHeight = Math.max(1, (val / 100) * (height - 20));
            const color = val === 0 && snap[field] === null
              ? "#3f3f46"  // NULL → gray
              : quotaBarColor(val);
            return (
              <View
                key={i}
                style={{
                  width: barWidth,
                  height: barHeight,
                  backgroundColor: color,
                  borderRadius: 1,
                  marginRight: gap,
                  alignSelf: "flex-end",
                }}
              />
            );
          })}
        </View>
      </View>
      <View style={sparkStyles.xAxis}>
        <Text style={sparkStyles.xLabel}>{firstTs}</Text>
        <Text style={sparkStyles.xLabel}>{midTs}</Text>
        <Text style={sparkStyles.xLabel}>{lastTs}</Text>
      </View>
    </View>
  );
}

const sparkStyles = StyleSheet.create({
  container: {
    marginBottom: 16,
  },
  label: {
    color: "#a1a1aa",
    fontSize: 12,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  chartArea: {
    backgroundColor: "#18181b",
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingTop: 8,
    paddingBottom: 4,
    justifyContent: "flex-end",
  },
  barsRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    flex: 1,
  },
  emptyText: {
    color: "#52525b",
    fontSize: 13,
    textAlign: "center",
    alignSelf: "center",
  },
  xAxis: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 4,
    marginTop: 4,
  },
  xLabel: {
    color: "#52525b",
    fontSize: 10,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
});

// ---------------------------------------------------------------------------
// Expanded quota bar (larger version for detail screen)
// ---------------------------------------------------------------------------

function ExpandedBar({
  label,
  utilization,
  resetsAt,
  subtitle,
}: {
  label: string;
  utilization: number;
  resetsAt: string;
  subtitle?: string;
}) {
  return (
    <View style={barStyles.barRow}>
      <View style={barStyles.labelRow}>
        <Text style={barStyles.label}>{label}</Text>
        <Text style={barStyles.percentage}>
          {Math.round(utilization)}%
        </Text>
      </View>
      <View style={barStyles.barTrack}>
        <View
          style={[
            barStyles.barFill,
            {
              width: `${Math.min(100, utilization)}%`,
              backgroundColor: quotaBarColor(utilization),
            },
          ]}
        />
      </View>
      {subtitle ? (
        <Text style={barStyles.resetText}>{subtitle}</Text>
      ) : (
        <Text style={barStyles.resetText}>
          Resets in {formatResetTime(resetsAt)}
        </Text>
      )}
    </View>
  );
}

const barStyles = StyleSheet.create({
  barRow: {
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  labelRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  label: {
    color: "#fafafa",
    fontSize: 15,
    fontWeight: "600",
  },
  percentage: {
    color: "#fafafa",
    fontSize: 15,
    fontWeight: "600",
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  barTrack: {
    height: 12,
    backgroundColor: "#27272a",
    borderRadius: 6,
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    borderRadius: 6,
  },
  resetText: {
    color: "#71717a",
    fontSize: 12,
    marginTop: 4,
  },
});

// ---------------------------------------------------------------------------
// Time range picker
// ---------------------------------------------------------------------------

const TIME_RANGES = [
  { label: "24h", hours: 24 },
  { label: "3d", hours: 72 },
  { label: "7d", hours: 168 },
] as const;

function TimeRangePicker({
  activeHours,
  onSelect,
  disabled,
}: {
  activeHours: number;
  onSelect: (hours: number) => void;
  disabled: boolean;
}) {
  return (
    <View style={pickerStyles.row}>
      {TIME_RANGES.map((r) => (
        <Pressable
          key={r.hours}
          style={[
            pickerStyles.btn,
            activeHours === r.hours && pickerStyles.btnActive,
          ]}
          onPress={() => onSelect(r.hours)}
          disabled={disabled}
        >
          <Text
            style={[
              pickerStyles.btnText,
              activeHours === r.hours && pickerStyles.btnTextActive,
            ]}
          >
            {r.label}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const pickerStyles = StyleSheet.create({
  row: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 16,
  },
  btn: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: "#27272a",
  },
  btnActive: {
    backgroundColor: "#3b82f6",
  },
  btnText: {
    color: "#a1a1aa",
    fontSize: 13,
    fontWeight: "600",
  },
  btnTextActive: {
    color: "#ffffff",
  },
});

// ---------------------------------------------------------------------------
// Heavy hitters — sessions that consumed the most between snapshots
// ---------------------------------------------------------------------------

/** Group heavy sessions by window, show delta + top sessions */
function HeavyHitters({ sessions }: { sessions: QuotaHeavySession[] }) {
  if (sessions.length === 0) return null;

  // Group by window
  const windows: Map<string, { start: string; end: string; fhDelta: number; sdDelta: number; sessions: QuotaHeavySession[] }> = new Map();
  for (const s of sessions) {
    const key = `${s.window_start}|${s.window_end}`;
    if (!windows.has(key)) {
      windows.set(key, {
        start: s.window_start,
        end: s.window_end,
        fhDelta: s.five_hour_delta,
        sdDelta: s.seven_day_delta,
        sessions: [],
      });
    }
    windows.get(key)!.sessions.push(s);
  }

  // Sort windows by time descending (most recent first)
  const sortedWindows = Array.from(windows.values()).sort(
    (a, b) => new Date(b.end).getTime() - new Date(a.end).getTime(),
  );

  return (
    <View style={hhStyles.container}>
      <Text style={hhStyles.sectionLabel}>HEAVY HITTERS</Text>
      {sortedWindows.map((w, wi) => {
        const startTime = new Date(w.start).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
        const endTime = new Date(w.end).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
        const hasDelta = w.fhDelta > 0 || w.sdDelta > 0;
        return (
          <View key={wi} style={hhStyles.window}>
            <View style={hhStyles.windowHeader}>
              <Text style={hhStyles.windowTime}>{startTime} → {endTime}</Text>
              {hasDelta && (
                <Text style={[
                  hhStyles.windowDelta,
                  w.fhDelta > 10 ? { color: "#ef4444" } : w.fhDelta > 5 ? { color: "#eab308" } : {},
                ]}>
                  5h: +{w.fhDelta}%  7d: +{w.sdDelta}%
                </Text>
              )}
            </View>
            {w.sessions.map((s, si) => {
              const name = s.session_name.replace(/^(imessage|signal|dispatch-app)\//, "");
              const shortName = name.length > 20 ? name.slice(0, 8) + "…" + name.slice(-8) : name;
              return (
                <View key={si} style={hhStyles.sessionRow}>
                  <View style={hhStyles.sessionInfo}>
                    <Text style={hhStyles.sessionName} numberOfLines={1}>
                      {shortName}
                    </Text>
                    <Text style={hhStyles.sessionMeta}>
                      {s.event_count} events · {s.duration_sec.toFixed(0)}s
                    </Text>
                  </View>
                  {s.tools.length > 0 && (
                    <Text style={hhStyles.toolsText} numberOfLines={1}>
                      {s.tools.slice(0, 4).join(", ")}
                      {s.tools.length > 4 ? ` +${s.tools.length - 4}` : ""}
                    </Text>
                  )}
                </View>
              );
            })}
          </View>
        );
      })}
    </View>
  );
}

const hhStyles = StyleSheet.create({
  container: {
    marginTop: 8,
    marginBottom: 16,
  },
  sectionLabel: {
    color: "#71717a",
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 1,
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  window: {
    backgroundColor: "#18181b",
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
  },
  windowHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  windowTime: {
    color: "#a1a1aa",
    fontSize: 12,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  windowDelta: {
    color: "#71717a",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  sessionRow: {
    paddingVertical: 4,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
  },
  sessionInfo: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  sessionName: {
    color: "#fafafa",
    fontSize: 13,
    fontWeight: "500",
    flex: 1,
  },
  sessionMeta: {
    color: "#71717a",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    marginLeft: 8,
  },
  toolsText: {
    color: "#52525b",
    fontSize: 11,
    marginTop: 2,
  },
});

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

export default function QuotaDetailScreen() {
  const [data, setData] = useState<QuotaHistoryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const mountedRef = useRef(true);

  const load = useCallback(
    async (h: number, refresh = false) => {
      if (refresh) setIsRefreshing(true);
      try {
        const result = await getDashboardQuotaHistory(h);
        if (mountedRef.current) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err.message : "Failed to load");
        }
      } finally {
        if (mountedRef.current) {
          setIsLoading(false);
          setIsRefreshing(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    load(hours);
    return () => {
      mountedRef.current = false;
    };
  }, [load, hours]);

  const handleTimeRange = useCallback(
    (h: number) => {
      if (h === hours || isLoading) return;
      setHours(h);
      setIsLoading(true);
      load(h);
    },
    [hours, isLoading, load],
  );

  const handleRefresh = useCallback(() => {
    load(hours, true);
  }, [hours, load]);

  // Build quota bars from current_quota
  const quota = data?.current_quota;
  const bars: Array<{ label: string; utilization: number; resetsAt: string }> = [];
  if (quota?.five_hour) {
    bars.push({ label: "5-Hour", utilization: quota.five_hour.utilization, resetsAt: quota.five_hour.resets_at });
  }
  if (quota?.seven_day) {
    bars.push({ label: "7-Day", utilization: quota.seven_day.utilization, resetsAt: quota.seven_day.resets_at });
  }
  if ((quota as Record<string, unknown>)?.seven_day_opus) {
    const opus = (quota as Record<string, unknown>).seven_day_opus as { utilization: number; resets_at: string };
    bars.push({ label: "7-Day Opus", utilization: opus.utilization, resetsAt: opus.resets_at });
  }
  if (quota?.seven_day_sonnet) {
    bars.push({ label: "7-Day Sonnet", utilization: quota.seven_day_sonnet.utilization, resetsAt: quota.seven_day_sonnet.resets_at });
  }

  // Extra usage (overage spend)
  const extraUsage = (quota as Record<string, unknown>)?.extra_usage as {
    is_enabled: boolean;
    monthly_limit: number | null;
    used_credits: number | null;
    utilization: number | null;
  } | undefined;

  // Backoff / staleness status
  const backoff = data?.current_backoff;
  const failures = backoff?.consecutive_failures ?? 0;
  const quotaUpdated = data?._quota_updated_at;
  const snapshots = data?.snapshots ?? [];
  const lastSnapshotTs = snapshots.length > 0 ? snapshots[snapshots.length - 1].ts : null;
  const isStale = lastSnapshotTs
    ? Date.now() - new Date(lastSnapshotTs).getTime() > 20 * 60 * 1000
    : false;

  return (
    <>
      <Stack.Screen options={{ title: "Quota" }} />
      <View style={styles.container}>
        {isLoading && !data ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color="#71717a" />
          </View>
        ) : error && !data ? (
          <View style={styles.center}>
            <Text style={styles.errorText}>{error}</Text>
            <Pressable style={styles.retryBtn} onPress={() => load(hours)}>
              <Text style={styles.retryText}>Retry</Text>
            </Pressable>
          </View>
        ) : (
          <ScrollView
            contentContainerStyle={styles.scrollContent}
            refreshControl={
              <RefreshControl
                refreshing={isRefreshing}
                onRefresh={handleRefresh}
                tintColor="#71717a"
              />
            }
          >
            {error && (
              <View style={styles.errorBanner}>
                <Text style={styles.errorBannerText}>⚠️ {error}</Text>
              </View>
            )}

            {/* Expanded quota bars */}
            <View style={styles.card}>
              <Text style={styles.sectionHeader}>CURRENT QUOTA</Text>
              {bars.length > 0 ? (
                bars.map((bar, i) => (
                  <React.Fragment key={bar.label}>
                    {i > 0 && <View style={styles.separator} />}
                    <ExpandedBar
                      label={bar.label}
                      utilization={bar.utilization}
                      resetsAt={bar.resetsAt}
                    />
                  </React.Fragment>
                ))
              ) : (
                <Text style={styles.mutedText}>
                  {isLoading ? "Loading quota…" : "No quota data"}
                </Text>
              )}
            </View>

            {/* Extra usage card */}
            {extraUsage?.is_enabled && extraUsage.utilization != null && (
              <View style={styles.card}>
                <Text style={styles.sectionHeader}>EXTRA USAGE</Text>
                <ExpandedBar
                  label="Monthly Spend"
                  utilization={extraUsage.utilization}
                  resetsAt=""
                  subtitle={`$${((extraUsage.used_credits ?? 0) / 100).toFixed(2)} of $${((extraUsage.monthly_limit ?? 0) / 100).toFixed(2)} · Resets monthly`}
                />
              </View>
            )}

            {/* Time range picker */}
            <TimeRangePicker
              activeHours={hours}
              onSelect={handleTimeRange}
              disabled={isLoading}
            />

            {/* Sparkline charts */}
            <SparklineChart
              snapshots={snapshots}
              field="five_hour"
              label="5-HOUR QUOTA OVER TIME"
              height={120}
            />
            <SparklineChart
              snapshots={snapshots}
              field="seven_day"
              label="ROLLING 7-DAY QUOTA OVER TIME"
              height={120}
            />

            {/* Heavy hitters */}
            <HeavyHitters sessions={data?.heavy_sessions ?? []} />

            {/* Status footer */}
            <View style={styles.statusSection}>
              {failures > 0 ? (
                <Text style={styles.statusWarning}>
                  ⚠️ API unreachable — retrying in{" "}
                  {Math.round((backoff?.backoff_seconds ?? 900) / 60)}m ({failures}{" "}
                  {failures === 1 ? "failure" : "failures"})
                </Text>
              ) : quotaUpdated ? (
                <Text style={styles.statusOk}>
                  ✓ Quota healthy — fetched {formatAge(quotaUpdated)}
                </Text>
              ) : null}
              {isStale && (
                <Text style={styles.statusStale}>
                  ⚠ Latest snapshot is over 20 min old — fetcher may be down
                </Text>
              )}
              <Text style={styles.snapshotCount}>
                {snapshots.length} snapshots in range
              </Text>
            </View>
          </ScrollView>
        )}
      </View>
    </>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 32,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 48,
  },
  card: {
    backgroundColor: "#18181b",
    borderRadius: 12,
    paddingVertical: 12,
    marginBottom: 16,
  },
  sectionHeader: {
    color: "#71717a",
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 1,
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#27272a",
    marginHorizontal: 16,
  },
  mutedText: {
    color: "#52525b",
    fontSize: 14,
    textAlign: "center",
    paddingVertical: 16,
  },
  statusSection: {
    marginTop: 8,
    paddingHorizontal: 4,
  },
  statusOk: {
    color: "#22c55e",
    fontSize: 12,
    marginBottom: 4,
  },
  statusWarning: {
    color: "#eab308",
    fontSize: 12,
    marginBottom: 4,
  },
  statusStale: {
    color: "#f59e0b",
    fontSize: 12,
    marginBottom: 4,
  },
  snapshotCount: {
    color: "#52525b",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    marginTop: 4,
  },
  errorText: {
    color: "#fafafa",
    fontSize: 16,
    textAlign: "center",
    marginBottom: 12,
  },
  retryBtn: {
    paddingHorizontal: 24,
    paddingVertical: 10,
    backgroundColor: "#3b82f6",
    borderRadius: 8,
  },
  retryText: {
    color: "#ffffff",
    fontSize: 14,
    fontWeight: "600",
  },
  errorBanner: {
    backgroundColor: "#7f1d1d",
    padding: 10,
    borderRadius: 8,
    marginBottom: 12,
  },
  errorBannerText: {
    color: "#fca5a5",
    fontSize: 13,
  },
});
