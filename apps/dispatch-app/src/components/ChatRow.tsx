import React, { useEffect, useRef } from "react";
import { Animated, StyleSheet, Text, View, Pressable } from "react-native";
import type { Conversation } from "../api/types";
import { relativeTime } from "../utils/time";

interface ChatRowProps {
  conversation: Conversation;
  onPress: () => void;
  onLongPress?: () => void;
  /** Force-mark as read (optimistic read) */
  forceRead?: boolean;
}

export function ChatRow({ conversation, onPress, onLongPress, forceRead }: ChatRowProps) {
  const { title, last_message, last_message_at, last_message_role, last_opened_at, is_thinking } =
    conversation;

  // Chat is "unread" only when the agent sent a message the user hasn't seen yet.
  // User's own messages never trigger unread — only assistant messages do.
  // forceRead overrides everything (optimistic read when user taps into chat).
  const isUnread = forceRead
    ? false
    : last_message_role === "assistant" && last_message_at
      ? last_opened_at
        ? new Date(last_message_at) > new Date(last_opened_at)
        : true  // No last_opened_at yet — assistant message is unread
      : false;

  // Build preview text with "You: " prefix for user messages
  let preview = "";
  if (last_message) {
    const prefix = last_message_role === "user" ? "You: " : "";
    preview = prefix + last_message;
  }

  // Generate initials for avatar — strip non-alphanumeric leading chars
  // so "[App] Sessions" gives "AS" not "[S"
  const initials = title
    .split(/\s+/)
    .map((w) => w.replace(/^[^a-zA-Z0-9]+/, ""))
    .filter((w) => w.length > 0)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  const timestamp = relativeTime(last_message_at);

  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
    >
      {isUnread ? (
        <View style={styles.unreadDot} />
      ) : (
        <View style={styles.unreadDotSpacer} />
      )}
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>{initials || "?"}</Text>
      </View>
      <View style={styles.content}>
        <View style={styles.topRow}>
          <Text style={[styles.title, isUnread && styles.titleUnread]} numberOfLines={1}>
            {title}
          </Text>
          {timestamp ? (
            <Text style={[styles.time, isUnread && styles.timeUnread]}>{timestamp}</Text>
          ) : null}
        </View>
        {is_thinking ? (
          <TypingDots />
        ) : preview ? (
          <Text style={[styles.preview, isUnread && styles.previewUnread]} numberOfLines={2}>
            {preview}
          </Text>
        ) : (
          <Text style={styles.emptyPreview}>No messages yet</Text>
        )}
      </View>
    </Pressable>
  );
}

/** Small pulsing dots for typing indicator in chat list */
function TypingDots() {
  const dot1 = useRef(new Animated.Value(0.3)).current;
  const dot2 = useRef(new Animated.Value(0.3)).current;
  const dot3 = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const pulse = (dot: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(dot, { toValue: 1, duration: 400, useNativeDriver: true }),
          Animated.timing(dot, { toValue: 0.3, duration: 400, useNativeDriver: true }),
        ]),
      );

    const a1 = pulse(dot1, 0);
    const a2 = pulse(dot2, 200);
    const a3 = pulse(dot3, 400);
    a1.start();
    a2.start();
    a3.start();

    return () => { a1.stop(); a2.stop(); a3.stop(); };
  }, [dot1, dot2, dot3]);

  return (
    <View style={styles.typingRow}>
      <Animated.View style={[styles.typingDot, { opacity: dot1 }]} />
      <Animated.View style={[styles.typingDot, { opacity: dot2 }]} />
      <Animated.View style={[styles.typingDot, { opacity: dot3 }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingRight: 16,
    paddingLeft: 4,
    paddingVertical: 12,
    backgroundColor: "#18181b",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  pressed: {
    backgroundColor: "#27272a",
  },
  unreadDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: "#3478f6",
    marginRight: 6,
  },
  unreadDotSpacer: {
    width: 10,
    marginRight: 6,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#3f3f46",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  avatarText: {
    color: "#d4d4d8",
    fontSize: 16,
    fontWeight: "600",
  },
  content: {
    flex: 1,
    justifyContent: "center",
  },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 3,
  },
  title: {
    color: "#fafafa",
    fontSize: 16,
    fontWeight: "400",
    flex: 1,
    marginRight: 8,
  },
  titleUnread: {
    fontWeight: "700",
  },
  time: {
    color: "#71717a",
    fontSize: 13,
  },
  timeUnread: {
    color: "#3478f6",
  },
  preview: {
    color: "#a1a1aa",
    fontSize: 14,
    lineHeight: 19,
  },
  previewUnread: {
    color: "#d4d4d8",
  },
  emptyPreview: {
    color: "#52525b",
    fontSize: 14,
    fontStyle: "italic",
  },
  typingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    height: 19,
  },
  typingDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: "#a1a1aa",
  },
});
