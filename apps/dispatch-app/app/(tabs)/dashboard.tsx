import React from "react";
import {
  ActivityIndicator,
  Animated,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { router } from "expo-router";
import { useDashboard } from "@/src/hooks/useDashboard";
import type { HistogramBucket } from "@/src/hooks/useDashboard";
import type { DashboardHealth, DashboardCcuResponse, SessionHealthSummary } from "@/src/api/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatUptime(seconds: number): string {
  if (seconds <= 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
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

function healthColor(status: string): string {
  switch (status) {
    case "healthy":
      return "#22c55e";
    case "degraded":
      return "#eab308";
    case "down":
      return "#ef4444";
    default:
      return "#71717a";
  }
}

function healthLabel(status: string): string {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "degraded":
      return "Degraded";
    case "down":
      return "Down";
    default:
      return "Unknown";
  }
}

function quotaBarColor(util: number): string {
  if (util >= 80) return "#ef4444";
  if (util >= 50) return "#eab308";
  return "#22c55e";
}

// Signal socket staleness threshold (seconds)
const SIGNAL_SOCKET_STALE_THRESHOLD = 600;

function watchdogColor(health: DashboardHealth): string {
  if (!health.watchdog_running) return "#ef4444";
  if (health.watchdog_crash_count > 0 || health.watchdog_backoff_seconds > 0) return "#eab308";
  return "#22c55e";
}

function watchdogSubtext(health: DashboardHealth): string {
  if (!health.watchdog_running) return "down";
  if (health.watchdog_backoff_seconds > 0) return "recovering...";
  if (health.watchdog_crash_count > 0) return `⚠ ${health.watchdog_crash_count} crash${health.watchdog_crash_count > 1 ? "es" : ""}`;
  if (health.watchdog_last_check_seconds != null) return `last: ${formatAge(health.watchdog_last_check_seconds)}`;
  return "—";
}

function signalColor(health: DashboardHealth): string {
  if (!health.signal_running) return "#ef4444";
  if (health.signal_socket_age_seconds != null && health.signal_socket_age_seconds > SIGNAL_SOCKET_STALE_THRESHOLD) return "#eab308";
  return "#22c55e";
}

function signalSubtext(health: DashboardHealth): string {
  if (!health.signal_running) return "down";
  if (health.signal_socket_age_seconds != null) return `sock: ${formatAge(health.signal_socket_age_seconds)}`;
  return "—";
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

function sessionHealthDotColor(status: string): string {
  if (status === "unhealthy") return "#ef4444";
  if (status === "degraded") return "#eab308";
  return "#22c55e";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Inline usage bar matching the settings.tsx pattern */
function UsageBar({
  label,
  utilization,
  resetsAt,
}: {
  label: string;
  utilization: number;
  resetsAt: string;
}) {
  return (
    <View style={usageStyles.barRow}>
      <View style={usageStyles.labelRow}>
        <Text style={usageStyles.label}>{label}</Text>
        <Text style={usageStyles.percentage}>
          {Math.round(utilization)}%
        </Text>
      </View>
      <View style={usageStyles.barTrack}>
        <View
          style={[
            usageStyles.barFill,
            {
              width: `${Math.min(100, utilization)}%`,
              backgroundColor: quotaBarColor(utilization),
            },
          ]}
        />
      </View>
      <Text style={usageStyles.resetText}>Resets in {formatResetTime(resetsAt)}</Text>
    </View>
  );
}

/** Estimated usage bar (same visual as UsageBar but shows value instead of %) */
function EstimatedBar({
  label,
  value,
  pct,
}: {
  label: string;
  value: string;
  pct: number;
}) {
  return (
    <View style={usageStyles.barRow}>
      <View style={usageStyles.labelRow}>
        <Text style={usageStyles.label}>{label}</Text>
        <Text style={usageStyles.percentage}>{value}</Text>
      </View>
      <View style={usageStyles.barTrack}>
        <View
          style={[
            usageStyles.barFill,
            {
              width: `${Math.min(100, pct)}%`,
              backgroundColor: quotaBarColor(pct),
            },
          ]}
        />
      </View>
    </View>
  );
}

/** Skeleton placeholder for loading state */
function SkeletonCard({ rows = 3 }: { rows?: number }) {
  const pulseAnim = React.useRef(new Animated.Value(0.3)).current;

  React.useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 0.7,
          duration: 800,
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 0.3,
          duration: 800,
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulseAnim]);

  return (
    <View style={styles.sectionCard}>
      {Array.from({ length: rows }).map((_, i) => (
        <React.Fragment key={i}>
          {i > 0 && <View style={styles.separator} />}
          <View style={styles.row}>
            <Animated.View
              style={[styles.skeletonBar, { opacity: pulseAnim }]}
            />
          </View>
        </React.Fragment>
      ))}
    </View>
  );
}

/** Row that navigates to a detail screen */
function NavRow({
  label,
  value,
  route,
}: {
  label: string;
  value?: string;
  route?: string;
}) {
  return (
    <Pressable
      style={({ pressed }) => [
        styles.row,
        pressed && styles.rowPressed,
      ]}
      onPress={route ? () => router.push(route as never) : undefined}
      disabled={!route}
    >
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.rowRight}>
        {value ? <Text style={styles.rowValue}>{value}</Text> : null}
        {route ? <Text style={styles.chevron}>›</Text> : null}
      </View>
    </Pressable>
  );
}

/** Info row (non-navigable, just label + value) */
function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Mini area chart (View-based, no external deps)
// ---------------------------------------------------------------------------

const CHART_HEIGHT = 48;
const CHART_BAR_GAP = 1;

function formatChartHour(iso: string): string {
  const d = new Date(iso);
  const h = d.getHours();
  const ampm = h >= 12 ? "p" : "a";
  const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${h12}${ampm}`;
}

function MiniAreaChart({ buckets }: { buckets: HistogramBucket[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.count));
  const total = buckets.reduce((s, b) => s + b.count, 0);

  if (buckets.length === 0) return null;

  // Pick ~5 evenly spaced labels from the bucket timestamps
  const labelCount = 5;
  const labels: { index: number; text: string }[] = [];
  for (let i = 0; i < labelCount; i++) {
    const idx = Math.round((i / (labelCount - 1)) * (buckets.length - 1));
    labels.push({ index: idx, text: formatChartHour(buckets[idx].hour) });
  }

  return (
    <View style={chartStyles.container}>
      <View style={chartStyles.labelRow}>
        <Text style={chartStyles.title}>Events (24h)</Text>
        <Text style={chartStyles.total}>{total.toLocaleString()}</Text>
      </View>
      <View style={chartStyles.chart}>
        {buckets.map((b, i) => {
          const h = Math.max(1, (b.count / max) * CHART_HEIGHT);
          const isRecent = i >= buckets.length - 1;
          return (
            <View
              key={i}
              style={[
                chartStyles.bar,
                {
                  height: h,
                  backgroundColor: isRecent ? "#3b82f6" : "#2563eb80",
                  marginRight: i < buckets.length - 1 ? CHART_BAR_GAP : 0,
                },
              ]}
            />
          );
        })}
      </View>
      <View style={chartStyles.xLabels}>
        {labels.map((l, i) => (
          <Text key={i} style={chartStyles.xLabel}>{l.text}</Text>
        ))}
      </View>
    </View>
  );
}

const chartStyles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  labelRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  title: {
    color: "#a1a1aa",
    fontSize: 13,
    fontWeight: "500",
  },
  total: {
    color: "#fafafa",
    fontSize: 13,
    fontWeight: "600",
  },
  chart: {
    flexDirection: "row",
    alignItems: "flex-end",
    height: CHART_HEIGHT,
  },
  bar: {
    flex: 1,
    borderRadius: 1.5,
    minWidth: 2,
  },
  xLabels: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 4,
  },
  xLabel: {
    color: "#52525b",
    fontSize: 10,
  },
});

// ---------------------------------------------------------------------------
// Subsystems row (Daemon / Watchdog / Signal)
// ---------------------------------------------------------------------------

function SubsystemsRow({ health }: { health: DashboardHealth }) {
  const daemonColor = healthColor(health.health_status);
  const wdColor = watchdogColor(health);
  const sigColor = signalColor(health);

  return (
    <View style={subsystemStyles.container}>
      <View style={subsystemStyles.item}>
        <View style={subsystemStyles.labelRow}>
          <View style={[styles.statusDot, { backgroundColor: daemonColor }]} />
          <Text style={subsystemStyles.label}>Daemon</Text>
        </View>
        <Text style={subsystemStyles.subtext}>{formatUptime(health.uptime_seconds)}</Text>
      </View>
      <View style={subsystemStyles.item}>
        <View style={subsystemStyles.labelRow}>
          <View style={[styles.statusDot, { backgroundColor: wdColor }]} />
          <Text style={subsystemStyles.label}>Watchdog</Text>
        </View>
        <Text style={subsystemStyles.subtext}>{watchdogSubtext(health)}</Text>
      </View>
      <View style={subsystemStyles.item}>
        <View style={subsystemStyles.labelRow}>
          <View style={[styles.statusDot, { backgroundColor: sigColor }]} />
          <Text style={subsystemStyles.label}>Signal</Text>
        </View>
        <Text style={subsystemStyles.subtext}>{signalSubtext(health)}</Text>
      </View>
    </View>
  );
}

const subsystemStyles = StyleSheet.create({
  container: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  item: {
    alignItems: "center",
    flex: 1,
  },
  labelRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    marginBottom: 3,
  },
  label: {
    color: "#a1a1aa",
    fontSize: 13,
    fontWeight: "500",
  },
  subtext: {
    color: "#52525b",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
});

// ---------------------------------------------------------------------------
// Health dots for sessions
// ---------------------------------------------------------------------------

function HealthDots({ sessionHealth }: { sessionHealth: SessionHealthSummary }) {
  const total = sessionHealth.healthy + sessionHealth.degraded + sessionHealth.unhealthy;
  if (total === 0) return null;

  // Build array of colors
  const dots: string[] = [];
  for (let i = 0; i < sessionHealth.healthy; i++) dots.push("#22c55e");
  for (let i = 0; i < sessionHealth.degraded; i++) dots.push("#eab308");
  for (let i = 0; i < sessionHealth.unhealthy; i++) dots.push("#ef4444");

  return (
    <View style={healthDotStyles.container}>
      {dots.map((color, i) => (
        <View
          key={i}
          style={[healthDotStyles.dot, { backgroundColor: color }]}
        />
      ))}
    </View>
  );
}

const healthDotStyles = StyleSheet.create({
  container: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 3,
    paddingHorizontal: 16,
    paddingBottom: 12,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
});

// ---------------------------------------------------------------------------
// Section renderers (memoized)
// ---------------------------------------------------------------------------

function DaemonWarningBanner({ running }: { running: boolean }) {
  if (running) return null;
  return (
    <View style={styles.warningBanner}>
      <Text style={styles.warningText}>⚠️ Daemon is not running</Text>
    </View>
  );
}

function SystemStatusSection({
  health,
  histogram,
}: {
  health: DashboardHealth;
  histogram: HistogramBucket[];
}) {
  const statusColor = healthColor(health.health_status);
  return (
    <View style={styles.section}>
      <Text style={styles.sectionHeader}>SYSTEM STATUS</Text>
      <View style={styles.sectionCard}>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>Status</Text>
          <View style={styles.statusRow}>
            <View
              style={[styles.statusDot, { backgroundColor: statusColor }]}
            />
            <Text style={[styles.statusText, { color: statusColor }]}>
              {healthLabel(health.health_status)}
            </Text>
          </View>
        </View>
        <View style={styles.separator} />
        <InfoRow label="Uptime" value={formatUptime(health.uptime_seconds)} />
        {histogram.length > 0 && (
          <>
            <View style={styles.separator} />
            <MiniAreaChart buckets={histogram} />
          </>
        )}
        <View style={styles.separator} />
        <SubsystemsRow health={health} />
      </View>
    </View>
  );
}

function formatCost(usd: number): string {
  if (usd >= 1000) return `$${(usd / 1000).toFixed(1)}k`;
  if (usd >= 100) return `$${Math.round(usd)}`;
  if (usd >= 10) return `$${usd.toFixed(1)}`;
  return `$${usd.toFixed(2)}`;
}

function UsageSection({
  ccu,
  loading,
  onRefresh,
}: {
  ccu: DashboardCcuResponse | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  const quota = ccu?.quota;
  // Build an ordered list of quota bars to display
  const bars: Array<{ label: string; utilization: number; resetsAt: string }> = [];
  if (quota?.five_hour) {
    bars.push({ label: "5-Hour", utilization: quota.five_hour.utilization, resetsAt: quota.five_hour.resets_at });
  }
  if (quota?.seven_day) {
    bars.push({ label: "7-Day", utilization: quota.seven_day.utilization, resetsAt: quota.seven_day.resets_at });
  }
  if (quota?.seven_day_opus) {
    bars.push({ label: "7-Day Opus", utilization: quota.seven_day_opus.utilization, resetsAt: quota.seven_day_opus.resets_at });
  }
  if (quota?.seven_day_sonnet) {
    bars.push({ label: "7-Day Sonnet", utilization: quota.seven_day_sonnet.utilization, resetsAt: quota.seven_day_sonnet.resets_at });
  }

  // Extra usage (monthly spend) bar
  const extraUsage = (quota as Record<string, unknown> | null)?.extra_usage as {
    is_enabled: boolean;
    monthly_limit: number | null;
    used_credits: number | null;
    utilization: number | null;
  } | undefined;
  const extraUsageBar = extraUsage?.is_enabled && extraUsage.utilization != null
    ? {
        label: "Monthly Spend",
        value: `$${(extraUsage.used_credits ?? 0).toFixed(0)} / $${(extraUsage.monthly_limit ?? 0).toFixed(0)}`,
        pct: extraUsage.utilization,
      }
    : null;

  // Extract active block data for estimated bars when quota is unavailable
  const activeBlock = ccu?.active_block as Record<string, unknown> | null;
  const blockTokens = (activeBlock?.totalTokens as number) ?? 0;
  const maxTokens = (ccu as Record<string, unknown> | null)?.max_tokens_observed as number ?? 0;
  const blockCost = activeBlock?.costUSD as number | undefined;
  const burnRate = activeBlock?.burnRate as { costPerHour?: number } | null;
  const projection = activeBlock?.projection as { totalCost?: number; remainingMinutes?: number } | null;
  const dailyTotals = ccu?.daily_totals as { totalCost?: number } | undefined;

  const hasBlockData = blockCost != null;

  // Build estimated bars from local CCU data
  const estimatedBars: Array<{ label: string; value: string; pct: number }> = [];
  if (hasBlockData) {
    // 5h block: tokens as % of historical max
    const blockPct = maxTokens > 0 ? Math.min(100, (blockTokens / maxTokens) * 100) : 0;
    estimatedBars.push({
      label: "5h Block",
      value: formatCost(blockCost!),
      pct: blockPct,
    });
    // Burn rate bar: cost/hr scaled ($200/hr = 100%)
    if (burnRate?.costPerHour != null) {
      const burnPct = Math.min(100, (burnRate.costPerHour / 200) * 100);
      estimatedBars.push({
        label: "Burn Rate",
        value: `${formatCost(burnRate.costPerHour)}/hr`,
        pct: burnPct,
      });
    }
    // 7-day total: scaled ($10,000 = 100%)
    if (dailyTotals?.totalCost != null) {
      const weekPct = Math.min(100, (dailyTotals.totalCost / 10000) * 100);
      estimatedBars.push({
        label: "7-Day",
        value: formatCost(dailyTotals.totalCost),
        pct: weekPct,
      });
    }
  }

  return (
    <Pressable style={styles.section} onPress={() => router.push("/dashboard/quota" as never)}>
      <View style={styles.sectionHeaderRow}>
        <Text style={styles.sectionHeader}>USAGE & QUOTA</Text>
        {loading && (
          <ActivityIndicator size="small" color="#71717a" style={styles.headerSpinner} />
        )}
      </View>
      <View style={styles.sectionCard}>
        {bars.length > 0 ? (
          <View style={styles.quotaContainer}>
            {bars.map((bar, i) => (
              <React.Fragment key={bar.label}>
                {i > 0 && <View style={styles.quotaSeparator} />}
                <UsageBar
                  label={bar.label}
                  utilization={bar.utilization}
                  resetsAt={bar.resetsAt}
                />
              </React.Fragment>
            ))}
            {extraUsageBar && (
              <>
                <View style={styles.quotaSeparator} />
                <EstimatedBar
                  label={extraUsageBar.label}
                  value={extraUsageBar.value}
                  pct={extraUsageBar.pct}
                />
              </>
            )}
          </View>
        ) : estimatedBars.length > 0 ? (
          <View style={styles.quotaContainer}>
            <Text style={styles.estimateNotice}>
              Official quota unavailable — estimated from local data
            </Text>
            {estimatedBars.map((bar, i) => (
              <React.Fragment key={bar.label}>
                {i > 0 && <View style={styles.quotaSeparator} />}
                <EstimatedBar
                  label={bar.label}
                  value={bar.value}
                  pct={bar.pct}
                />
              </React.Fragment>
            ))}
          </View>
        ) : (
          <View style={styles.row}>
            <Text style={styles.rowValueMuted}>
              {ccu?._loading ? "Loading quota…" : "No quota data"}
            </Text>
          </View>
        )}
      </View>
      {(ccu?._quota_updated_at || ccu?._updated_at) && (
        <Text style={styles.sectionFooterMono}>
          Tap for details · Quota fetched {ccu._quota_updated_at
            ? new Date(ccu._quota_updated_at).toLocaleTimeString()
            : new Date(ccu._updated_at!).toLocaleTimeString()}
        </Text>
      )}
    </Pressable>
  );
}

function SessionsSection({ count, sessionHealth }: { count: number; sessionHealth?: SessionHealthSummary }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionHeader}>SESSIONS</Text>
      <View style={styles.sectionCard}>
        <NavRow
          label="Active Sessions"
          value={`${count}`}
          route="/dashboard/sessions"
        />
        {sessionHealth && (sessionHealth.healthy + sessionHealth.degraded + sessionHealth.unhealthy) > 0 && (
          <>
            <View style={styles.separator} />
            <HealthDots sessionHealth={sessionHealth} />
          </>
        )}
      </View>
    </View>
  );
}

function TasksSection({
  reminders,
  skills,
}: {
  reminders: number;
  skills: number;
}) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionHeader}>TASKS & KNOWLEDGE</Text>
      <View style={styles.sectionCard}>
        <NavRow
          label="Active Reminders"
          value={`${reminders}`}
          route="/dashboard/tasks"
        />
        <View style={styles.separator} />
        <NavRow
          label="Skills"
          value={`${skills}`}
          route="/dashboard/skills"
        />
      </View>
    </View>
  );
}

function SystemSection() {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionHeader}>SYSTEM</Text>
      <View style={styles.sectionCard}>
        <NavRow label="Logs" route="/logs" />
        <View style={styles.separator} />
        <NavRow label="Events" route="/dashboard/events" />
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Main Dashboard Screen
// ---------------------------------------------------------------------------

export default function DashboardScreen() {
  const { health, ccu, histogram, isLoading, ccuLoading, error, lastUpdated, refresh, refreshCcu } =
    useDashboard();

  // First load — no cached data yet
  if (isLoading && !health) {
    return (
      <View style={styles.container}>
        <ScrollView contentContainerStyle={styles.contentContainer}>
          <View style={styles.section}>
            <Text style={styles.sectionHeader}>SYSTEM STATUS</Text>
            <SkeletonCard rows={4} />
          </View>
          <View style={styles.section}>
            <Text style={styles.sectionHeader}>USAGE & QUOTA</Text>
            <SkeletonCard rows={2} />
          </View>
          <View style={styles.section}>
            <Text style={styles.sectionHeader}>SESSIONS</Text>
            <SkeletonCard rows={1} />
          </View>
        </ScrollView>
      </View>
    );
  }

  // Error with no cached data
  if (error && !health) {
    return (
      <View style={styles.container}>
        <View style={styles.errorContainer}>
          <Text style={styles.errorEmoji}>⚠️</Text>
          <Text style={styles.errorTitle}>Unable to load dashboard</Text>
          <Text style={styles.errorMessage}>{error}</Text>
          <Pressable style={styles.retryButton} onPress={refresh}>
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.contentContainer}
        refreshControl={
          <RefreshControl
            refreshing={isLoading}
            onRefresh={refresh}
            tintColor="#71717a"
          />
        }
      >
        {/* Error banner (stale-while-revalidate) */}
        {error && (
          <View style={styles.errorBanner}>
            <Text style={styles.errorBannerText}>
              ⚠️ {error}
            </Text>
          </View>
        )}

        {/* Daemon not running warning */}
        {health && <DaemonWarningBanner running={health.daemon_running} />}

        {/* Main sections */}
        {health && <SystemStatusSection health={health} histogram={histogram} />}
        <UsageSection ccu={ccu} loading={ccuLoading} onRefresh={refreshCcu} />
        {health && (
          <SessionsSection count={health.active_sessions} sessionHealth={health.session_health} />
        )}
        {health && (
          <TasksSection
            reminders={health.active_reminders}
            skills={health.skills_count}
          />
        )}
        <SystemSection />

        {/* Footer */}
        {lastUpdated && (
          <Text style={styles.footerText}>
            Last updated {lastUpdated.toLocaleTimeString()}
          </Text>
        )}
      </ScrollView>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const usageStyles = StyleSheet.create({
  barRow: {
    paddingHorizontal: 16,
    paddingVertical: 5,
  },
  labelRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  label: {
    color: "#fafafa",
    fontSize: 14,
    fontWeight: "500",
  },
  percentage: {
    color: "#a1a1aa",
    fontSize: 13,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  barTrack: {
    height: 6,
    backgroundColor: "#27272a",
    borderRadius: 3,
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    borderRadius: 3,
  },
  resetText: {
    color: "#52525b",
    fontSize: 11,
    marginTop: 3,
  },
});

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  contentContainer: {
    paddingBottom: 48,
  },

  // Sections
  section: {
    marginTop: 24,
    paddingHorizontal: 16,
  },
  sectionHeader: {
    color: "#71717a",
    fontSize: 13,
    fontWeight: "600",
    letterSpacing: 0.5,
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  headerSpinner: {
    marginBottom: 8,
  },
  sectionCard: {
    backgroundColor: "#18181b",
    borderRadius: 12,
    overflow: "hidden",
  },
  sectionFooterMono: {
    color: "#3f3f46",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    marginTop: 6,
    paddingHorizontal: 4,
  },

  // Rows
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 14,
    minHeight: 48,
  },
  rowPressed: {
    backgroundColor: "#27272a",
  },
  rowLabel: {
    color: "#fafafa",
    fontSize: 15,
  },
  rowRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  rowValue: {
    color: "#71717a",
    fontSize: 15,
  },
  rowValueMuted: {
    color: "#52525b",
    fontSize: 14,
  },
  chevron: {
    color: "#52525b",
    fontSize: 22,
    fontWeight: "300",
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#27272a",
    marginLeft: 16,
  },

  // Status
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusText: {
    fontSize: 15,
    fontWeight: "500",
  },

  // Quota
  quotaContainer: {
    paddingVertical: 6,
  },
  quotaSeparator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#27272a",
    marginHorizontal: 16,
    marginVertical: 2,
  },
  estimateNotice: {
    color: "#52525b",
    fontSize: 11,
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 4,
  },

  // Warning banner
  warningBanner: {
    backgroundColor: "#7f1d1d",
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 10,
  },
  warningText: {
    color: "#fca5a5",
    fontSize: 14,
    fontWeight: "600",
    textAlign: "center",
  },

  // Error states
  errorContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 32,
  },
  errorEmoji: {
    fontSize: 48,
    marginBottom: 16,
  },
  errorTitle: {
    color: "#fafafa",
    fontSize: 18,
    fontWeight: "600",
    marginBottom: 8,
  },
  errorMessage: {
    color: "#71717a",
    fontSize: 14,
    textAlign: "center",
    marginBottom: 24,
  },
  retryButton: {
    backgroundColor: "#2563eb",
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 10,
  },
  retryText: {
    color: "#fafafa",
    fontSize: 16,
    fontWeight: "600",
  },
  errorBanner: {
    backgroundColor: "#7f1d1d",
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 8,
  },
  errorBannerText: {
    color: "#fca5a5",
    fontSize: 13,
  },

  // Skeleton
  skeletonBar: {
    height: 14,
    width: "60%",
    backgroundColor: "#27272a",
    borderRadius: 4,
  },

  // Footer
  footerText: {
    color: "#3f3f46",
    fontSize: 11,
    textAlign: "center",
    marginTop: 24,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
});
