import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { SdkEvent } from "../api/types";

const MAX_PAYLOAD_LENGTH = 500;

interface SdkEventBubbleProps {
  event: SdkEvent;
}

export function SdkEventBubble({ event }: SdkEventBubbleProps) {
  const [expanded, setExpanded] = useState(false);
  const [showTimestamp, setShowTimestamp] = useState(false);

  const bgColor = getEventColor(event.event_type, event.is_error);

  const payload = event.payload || "";
  const isLong = payload.length > MAX_PAYLOAD_LENGTH;
  const displayPayload =
    isLong && !expanded ? payload.slice(0, MAX_PAYLOAD_LENGTH) + "..." : payload;

  return (
    <View style={styles.wrapper}>
      <Pressable
        onPress={() => setShowTimestamp((v) => !v)}
        style={[styles.bubble, { backgroundColor: bgColor }]}
      >
        <View style={styles.header}>
          <View
            style={[
              styles.badge,
              {
                backgroundColor: getBadgeColor(
                  event.event_type,
                  event.is_error,
                ),
              },
            ]}
          >
            <Text style={styles.badgeText}>{event.event_type}</Text>
          </View>
          {event.tool_name ? (
            <Text style={styles.toolName}>{event.tool_name}</Text>
          ) : null}
          {event.duration_ms != null ? (
            <Text style={styles.duration}>
              {Math.round(event.duration_ms)}ms
            </Text>
          ) : null}
        </View>
        {displayPayload ? (
          <Text style={styles.payload} selectable>
            {displayPayload}
          </Text>
        ) : null}
        {isLong ? (
          <Pressable onPress={() => setExpanded((v) => !v)} hitSlop={8}>
            <Text style={styles.expandToggle}>
              {expanded ? "Show less" : "Show more"}
            </Text>
          </Pressable>
        ) : null}
      </Pressable>
      {showTimestamp ? (
        <Text style={styles.timestamp}>
          {new Date(event.timestamp).toLocaleTimeString()}
          {event.num_turns != null ? ` · Turn ${event.num_turns}` : ""}
        </Text>
      ) : null}
    </View>
  );
}

function getEventColor(eventType: string, isError: boolean): string {
  if (isError) return "#450a0a";
  switch (eventType) {
    case "tool_use":
      return "#1e1b4b";
    case "tool_result":
      return "#052e16";
    case "result":
      return "#064e3b";
    default:
      return "#27272a";
  }
}

function getBadgeColor(eventType: string, isError: boolean): string {
  if (isError) return "#dc2626";
  switch (eventType) {
    case "tool_use":
      return "#4f46e5";
    case "tool_result":
      return "#16a34a";
    case "result":
      return "#059669";
    default:
      return "#52525b";
  }
}

const styles = StyleSheet.create({
  wrapper: {
    paddingHorizontal: 12,
    marginVertical: 2,
    alignItems: "flex-start",
  },
  bubble: {
    maxWidth: "95%",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 4,
  },
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  badgeText: {
    color: "#fff",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  toolName: {
    color: "#d4d4d8",
    fontSize: 13,
    fontWeight: "600",
  },
  duration: {
    color: "#a1a1aa",
    fontSize: 11,
  },
  payload: {
    color: "#d4d4d8",
    fontSize: 13,
    lineHeight: 18,
    fontFamily: "monospace",
  },
  expandToggle: {
    color: "#a1a1aa",
    fontSize: 12,
    fontWeight: "600",
    marginTop: 4,
  },
  timestamp: {
    color: "#71717a",
    fontSize: 11,
    marginTop: 2,
    marginHorizontal: 4,
  },
});
