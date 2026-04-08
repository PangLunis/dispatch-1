/**
 * View-based sparkline bar chart for quota utilization over time.
 *
 * Each bar is stacked (bottom-to-top via flexDirection: "column"):
 *   - Top segment (lighter): accumulated utilization level
 *   - Bottom segment (solid): delta increase since previous snapshot
 *
 * The chart filters snapshots to the natural quota window (5h or 7d)
 * and derives x-axis labels from actual snapshot timestamps.
 */
import React, { useMemo, useState } from "react";
import { Dimensions, Platform, StyleSheet, Text, View } from "react-native";
import { quotaBarColor, formatTimestamp } from "@/src/utils/quotaHelpers";
import type { QuotaSnapshot } from "@/src/api/types";

/** Maps quota field to its natural window duration in milliseconds */
const WINDOW_MS: Record<string, number> = {
  five_hour: 5 * 3600_000,
  seven_day: 7 * 24 * 3600_000,
};

export function SparklineChart({
  snapshots,
  field,
  label,
  height = 120,
  rangeHours,
  resetsAt,
}: {
  snapshots: QuotaSnapshot[];
  /** Which quota field to plot — determines both the data and the window filter */
  field: "five_hour" | "seven_day";
  label: string;
  height?: number;
  /** Controls timestamp label format (hours vs date+time) */
  rangeHours?: number;
  /** ISO timestamp when the current quota block ends — anchors the x-axis */
  resetsAt?: string;
}) {
  const [containerWidth, setContainerWidth] = useState(
    Dimensions.get("window").width - 48,
  );

  const windowMs = WINDOW_MS[field];

  // Window bounds: use resetsAt as the end, subtract window duration for start.
  // If resetsAt is in the past (stale data), fall back to Date.now() so we
  // still show recent snapshots instead of an empty "Collecting data" message.
  const resetsAtMs = resetsAt ? new Date(resetsAt).getTime() : 0;
  const isResetsAtFuture = resetsAtMs > Date.now();
  const windowEnd = isResetsAtFuture ? resetsAtMs : Date.now();
  const windowStart = windowEnd - windowMs;

  // Filter snapshots to the current quota block window
  const windowSnapshots = useMemo(() => {
    if (snapshots.length === 0) return [];
    const filtered = snapshots.filter((s) => {
      const t = new Date(s.ts).getTime();
      return t >= windowStart && t <= windowEnd;
    });
    // Fallback: if fewer than 2 snapshots in window, use last 2 available.
    return filtered.length >= 2 ? filtered : snapshots.slice(-Math.min(snapshots.length, 2));
  }, [snapshots, windowStart, windowEnd]);

  // Compute deltas between consecutive snapshots
  const barData = useMemo(() => {
    return windowSnapshots.map((snap, i) => {
      const totalVal = snap[field] ?? 0;
      const isNull = snap[field] === null;
      // Delta: positive = quota consumed since last snapshot
      let delta = 0;
      if (i > 0) {
        const prevVal = windowSnapshots[i - 1][field] ?? 0;
        delta = Math.max(0, totalVal - prevVal);
      }
      return { totalVal, delta, isNull };
    });
  }, [windowSnapshots, field]);

  if (windowSnapshots.length < 2) {
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

  const barWidth = Math.max(3, Math.floor(containerWidth / windowSnapshots.length) - 1);
  const gap = 1;
  const usableHeight = height - 20;
  const lastIdx = windowSnapshots.length - 1;

  // X-axis labels from quota block bounds (not snapshot timestamps)
  const startLabel = formatTimestamp(new Date(windowStart).toISOString(), rangeHours);
  const endLabel = formatTimestamp(new Date(windowEnd).toISOString(), rangeHours);

  // 80% threshold reference line
  const thresholdBottom = 0.8 * usableHeight + 4;

  return (
    <View style={sparkStyles.container}>
      <View style={sparkStyles.headerRow}>
        <Text style={sparkStyles.label}>{label}</Text>
        <View style={sparkStyles.legendRow}>
          <View style={[sparkStyles.legendDot, { backgroundColor: quotaBarColor(barData[barData.length - 1]?.totalVal ?? 0), opacity: 0.9 }]} />
          <Text style={sparkStyles.legendText}>delta</Text>
          <View style={[sparkStyles.legendDot, { backgroundColor: quotaBarColor(barData[barData.length - 1]?.totalVal ?? 0), opacity: 0.35 }]} />
          <Text style={sparkStyles.legendText}>level</Text>
        </View>
      </View>
      <View
        style={[sparkStyles.chartArea, { height }]}
        onLayout={(e) => setContainerWidth(e.nativeEvent.layout.width)}
      >
        <View style={[sparkStyles.thresholdLine, { bottom: thresholdBottom }]}>
          <Text style={sparkStyles.thresholdLabel}>80%</Text>
        </View>
        <View style={sparkStyles.barsRow}>
          {barData.map((d, i) => {
            const totalHeight = Math.max(1, (d.totalVal / 100) * usableHeight);
            const deltaHeight = Math.max(0, (d.delta / 100) * usableHeight);
            const levelHeight = Math.max(0, totalHeight - deltaHeight);
            const isLast = i === lastIdx;

            const color = d.isNull
              ? "#3f3f46"
              : quotaBarColor(d.totalVal);

            return (
              <View
                key={i}
                style={{
                  width: barWidth,
                  marginRight: gap,
                  alignSelf: "flex-end",
                  height: totalHeight,
                }}
              >
                {/* Level segment (top, lighter — accumulated utilization) */}
                <View
                  style={{
                    height: levelHeight,
                    backgroundColor: color,
                    borderTopLeftRadius: 1,
                    borderTopRightRadius: 1,
                    borderBottomLeftRadius: deltaHeight > 0 ? 0 : 1,
                    borderBottomRightRadius: deltaHeight > 0 ? 0 : 1,
                    opacity: isLast ? 0.4 : 0.35,
                  }}
                />
                {/* Delta segment (bottom, solid — increase since last snapshot) */}
                {deltaHeight > 0 && (
                  <View
                    style={{
                      height: deltaHeight,
                      backgroundColor: color,
                      borderBottomLeftRadius: 1,
                      borderBottomRightRadius: 1,
                      opacity: isLast ? 1 : 0.9,
                    }}
                  />
                )}
              </View>
            );
          })}
        </View>
      </View>
      <View style={sparkStyles.xAxis}>
        <Text style={sparkStyles.xLabel}>{startLabel}</Text>
        <Text style={sparkStyles.xLabelNow}>{isResetsAtFuture ? `resets ${endLabel}` : `now ${endLabel}`} ●</Text>
      </View>
    </View>
  );
}

const sparkStyles = StyleSheet.create({
  container: {
    marginBottom: 16,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  label: {
    color: "#a1a1aa",
    fontSize: 12,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  legendRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  legendDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  legendText: {
    color: "#52525b",
    fontSize: 9,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    marginRight: 6,
  },
  chartArea: {
    backgroundColor: "#18181b",
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingTop: 8,
    paddingBottom: 4,
    justifyContent: "flex-end",
    overflow: "hidden",
  },
  barsRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    flex: 1,
  },
  thresholdLine: {
    position: "absolute",
    left: 8,
    right: 8,
    height: 1,
    backgroundColor: "#3f3f46",
    flexDirection: "row",
    alignItems: "center",
  },
  thresholdLabel: {
    position: "absolute",
    right: 0,
    color: "#52525b",
    fontSize: 8,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    top: -10,
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
  xLabelNow: {
    color: "#a1a1aa",
    fontSize: 10,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    fontWeight: "600",
  },
});
