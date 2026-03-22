import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { branding } from "../config/branding";

const SOURCE_COLORS: Record<string, string> = {
  imessage: "#007AFF",
  signal: "#3A76F0",
  discord: "#5865F2",
  "dispatch-api": branding.accentColor,
};

const SOURCE_LABELS: Record<string, string> = {
  imessage: "iMessage",
  signal: "Signal",
  discord: "Discord",
  "dispatch-api": "Dispatch",
};

interface SourceBadgeProps {
  source: string;
}

export function SourceBadge({ source }: SourceBadgeProps) {
  const key = source.toLowerCase();
  const color = SOURCE_COLORS[key] ?? "#71717a";
  const label = SOURCE_LABELS[key] ?? source;

  return (
    <View style={[styles.badge, { backgroundColor: color + "22" }]}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.text, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    gap: 4,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  text: {
    fontSize: 10,
    fontWeight: "600",
  },
});
