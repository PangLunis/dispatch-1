import React from "react";
import { Pressable, ScrollView, StyleSheet, Text } from "react-native";
import { branding } from "../config/branding";

export type SourceFilter =
  | "all"
  | "imessage"
  | "signal"
  | "discord"
  | "dispatch-api";

const FILTERS: { key: SourceFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "imessage", label: "iMessage" },
  { key: "signal", label: "Signal" },
  { key: "discord", label: "Discord" },
  { key: "dispatch-api", label: "Dispatch" },
];

interface FilterPillsProps {
  selected: SourceFilter;
  onSelect: (filter: SourceFilter) => void;
}

export function FilterPills({ selected, onSelect }: FilterPillsProps) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.container}
      style={styles.scroll}
    >
      {FILTERS.map(({ key, label }) => {
        const isActive = selected === key;
        return (
          <Pressable
            key={key}
            onPress={() => onSelect(key)}
            style={[
              styles.pill,
              isActive && styles.pillActive,
            ]}
          >
            <Text
              style={[
                styles.pillText,
                isActive && styles.pillTextActive,
              ]}
            >
              {label}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 0,
  },
  container: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 8,
  },
  pill: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: "#27272a",
    borderWidth: 1,
    borderColor: "#3f3f46",
  },
  pillActive: {
    backgroundColor: branding.accentColor + "22",
    borderColor: branding.accentColor,
  },
  pillText: {
    color: "#a1a1aa",
    fontSize: 13,
    fontWeight: "500",
  },
  pillTextActive: {
    color: branding.accentColor,
    fontWeight: "600",
  },
});
