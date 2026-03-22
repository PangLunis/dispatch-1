import React from "react";
import { StyleSheet, Text, View } from "react-native";

const TIER_COLORS: Record<string, string> = {
  admin: "#d97706",
  partner: "#db2777",
  family: "#059669",
  favorite: "#2563eb",
  bots: "#7c3aed",
};

interface TierBadgeProps {
  tier: string;
}

export function TierBadge({ tier }: TierBadgeProps) {
  const color = TIER_COLORS[tier.toLowerCase()] ?? "#71717a";
  const label = tier.charAt(0).toUpperCase() + tier.slice(1).toLowerCase();

  return (
    <View style={[styles.badge, { backgroundColor: color + "22", borderColor: color }]}>
      <Text style={[styles.text, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
  },
  text: {
    fontSize: 10,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
});
