import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { AgentSession } from "../api/types";
import { SourceBadge } from "./SourceBadge";
import { relativeTime } from "../utils/time";

interface AgentSessionRowProps {
  session: AgentSession;
  onPress: () => void;
  onLongPress?: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  active: "#22c55e",
  idle: "#71717a",
  error: "#ef4444",
};

export function AgentSessionRow({
  session,
  onPress,
  onLongPress,
}: AgentSessionRowProps) {
  const { name, source, last_message, last_message_time, status } =
    session;

  // Generate initials for avatar — strip non-alphanumeric leading chars
  // so "[App] Sessions" gives "AS" not "[S"
  const initials = name
    .split(/\s+/)
    .map((w) => w.replace(/^[^a-zA-Z0-9]+/, ""))
    .filter((w) => w.length > 0)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  const statusColor = STATUS_COLORS[status] ?? "#71717a";
  const timestamp = relativeTime(last_message_time);

  // Build preview
  let preview = "";
  if (last_message) {
    const prefix = session.last_message_is_from_me ? "You: " : "";
    preview = prefix + last_message;
  }

  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
    >
      {/* Avatar with status dot */}
      <View style={styles.avatarContainer}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials || "?"}</Text>
        </View>
        <View
          style={[
            styles.statusDot,
            { backgroundColor: statusColor },
          ]}
        />
      </View>

      {/* Content */}
      <View style={styles.content}>
        <View style={styles.topRow}>
          <Text style={styles.name} numberOfLines={1}>
            {name}
          </Text>
          {timestamp ? (
            <Text style={styles.time}>{timestamp}</Text>
          ) : null}
        </View>

        {/* Source badge */}
        {source ? (
          <View style={styles.badgesRow}>
            <SourceBadge source={source} />
          </View>
        ) : null}

        {/* Preview */}
        {preview ? (
          <Text style={styles.preview} numberOfLines={1}>
            {preview}
          </Text>
        ) : (
          <Text style={styles.emptyPreview}>No messages yet</Text>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingRight: 16,
    paddingLeft: 16,
    paddingVertical: 12,
    backgroundColor: "#18181b",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  pressed: {
    backgroundColor: "#27272a",
  },
  avatarContainer: {
    position: "relative",
    marginRight: 12,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#3f3f46",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: {
    color: "#d4d4d8",
    fontSize: 16,
    fontWeight: "600",
  },
  statusDot: {
    position: "absolute",
    bottom: 0,
    right: 0,
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: "#18181b",
  },
  content: {
    flex: 1,
    justifyContent: "center",
  },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  name: {
    color: "#fafafa",
    fontSize: 16,
    fontWeight: "600",
    flex: 1,
    marginRight: 8,
  },
  time: {
    color: "#71717a",
    fontSize: 13,
  },
  badgesRow: {
    flexDirection: "row",
    gap: 6,
    marginBottom: 4,
  },
  preview: {
    color: "#a1a1aa",
    fontSize: 14,
    lineHeight: 19,
  },
  emptyPreview: {
    color: "#52525b",
    fontSize: 14,
    fontStyle: "italic",
  },
});
