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
import type { DashboardHealth, DashboardCcuResponse } from "@/src/api/types";

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
  const hours = Math.max(0, Math.floor(diffMs / 3_600_000));
  const mins = Math.max(0, Math.floor((diffMs % 3_600_000) / 60_000));
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

function SystemStatusSection({ health }: { health: DashboardHealth }) {
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
        <View style={styles.separator} />
        <InfoRow
          label="Events / Hour"
          value={`${health.events_last_hour}`}
        />
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

  // Extract active block data for fallback display
  const activeBlock = ccu?.active_block as Record<string, unknown> | null;
  const blockCost = activeBlock?.costUSD as number | undefined;
  const burnRate = activeBlock?.burnRate as { costPerHour?: number } | null;
  const projection = activeBlock?.projection as { totalCost?: number; remainingMinutes?: number } | null;
  const dailyTotals = ccu?.daily_totals as { totalCost?: number } | undefined;

  const hasBlockData = blockCost != null;

  return (
    <Pressable style={styles.section} onPress={onRefresh}>
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
          </View>
        ) : hasBlockData ? (
          <View style={styles.quotaContainer}>
            {/* Current 5h block cost */}
            <View style={styles.row}>
              <Text style={styles.rowLabel}>Current Block</Text>
              <Text style={styles.rowValue}>{formatCost(blockCost!)}</Text>
            </View>
            {/* Burn rate */}
            {burnRate?.costPerHour != null && (
              <>
                <View style={styles.separator} />
                <View style={styles.row}>
                  <Text style={styles.rowLabel}>Burn Rate</Text>
                  <Text style={styles.rowValue}>
                    {formatCost(burnRate.costPerHour)}/hr
                  </Text>
                </View>
              </>
            )}
            {/* Projected block cost */}
            {projection?.totalCost != null && (
              <>
                <View style={styles.separator} />
                <View style={styles.row}>
                  <Text style={styles.rowLabel}>Block Projection</Text>
                  <Text style={styles.rowValue}>
                    {formatCost(projection.totalCost)}
                    {projection.remainingMinutes != null &&
                      ` · ${projection.remainingMinutes}m left`}
                  </Text>
                </View>
              </>
            )}
            {/* 7-day rolling cost */}
            {dailyTotals?.totalCost != null && (
              <>
                <View style={styles.separator} />
                <View style={styles.row}>
                  <Text style={styles.rowLabel}>7-Day Total</Text>
                  <Text style={styles.rowValue}>
                    {formatCost(dailyTotals.totalCost)}
                  </Text>
                </View>
              </>
            )}
            {/* Quota error notice */}
            {ccu?._quota_error && (
              <>
                <View style={styles.separator} />
                <View style={styles.row}>
                  <Text style={[styles.rowValueMuted, { fontSize: 12 }]}>
                    Quota bars unavailable (rate limited)
                  </Text>
                </View>
              </>
            )}
          </View>
        ) : (
          <View style={styles.row}>
            <Text style={styles.rowValueMuted}>
              {ccu?._loading ? "Loading quota…" : "No quota data"}
            </Text>
          </View>
        )}
      </View>
      {ccu?._updated_at && (
        <Text style={styles.sectionFooterMono}>
          Tap to refresh · Updated {new Date(ccu._updated_at).toLocaleTimeString()}
        </Text>
      )}
    </Pressable>
  );
}

function SessionsSection({ count }: { count: number }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionHeader}>SESSIONS</Text>
      <View style={styles.sectionCard}>
        <NavRow
          label="Active Sessions"
          value={`${count}`}
          route="/dashboard/sessions"
        />
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
  const { health, ccu, isLoading, ccuLoading, error, lastUpdated, refresh, refreshCcu } =
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
        {health && <SystemStatusSection health={health} />}
        <UsageSection ccu={ccu} loading={ccuLoading} onRefresh={refreshCcu} />
        {health && (
          <SessionsSection count={health.active_sessions} />
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
