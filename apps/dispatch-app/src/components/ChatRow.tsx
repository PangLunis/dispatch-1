import React, { useCallback, useEffect, useRef } from "react";
import { Animated, StyleSheet, Text, View, Pressable } from "react-native";
import { Image } from "expo-image";
import type { Conversation } from "../api/types";
import { relativeTime } from "../utils/time";
import { PulsingDots } from "./PulsingDots";
import { buildImageUrl } from "../api/images";
import { useReduceMotion } from "../utils/animation";

interface ChatRowProps {
  conversation: Conversation;
  /** Called with conversation when row is pressed. Pass a stable useCallback to avoid re-renders. */
  onPress: (conversation: Conversation) => void;
  /** Called with conversation on long press. Pass a stable useCallback to avoid re-renders. */
  onLongPress?: (conversation: Conversation) => void;
  /** Pre-computed unread state (from isCurrentlyUnread in useChatList) */
  isUnread: boolean;
  /** Whether this row is the currently selected chat (desktop sidebar) */
  isSelected?: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  active: "#22c55e",
  idle: "#71717a",
};

export const ChatRow = React.memo(function ChatRow({ conversation, onPress, onLongPress, isUnread, isSelected }: ChatRowProps) {
  const { title, last_message, last_message_at, last_message_role, is_thinking, image_url, image_status, status } =
    conversation;

  // Compose stable per-item callbacks inside memo — avoids external cache.
  // Only re-created if conversation identity or parent callbacks change.
  const handlePress = useCallback(() => onPress(conversation), [onPress, conversation]);
  const handleLongPress = useCallback(() => onLongPress?.(conversation), [onLongPress, conversation]);

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

  // Animated press scale — 60fps via native driver, smoother than Pressable style
  const pressScale = useRef(new Animated.Value(1)).current;
  const handlePressIn = useCallback(() => {
    Animated.timing(pressScale, {
      toValue: 0.98,
      duration: 100,
      useNativeDriver: true,
    }).start();
  }, [pressScale]);
  const handlePressOut = useCallback(() => {
    Animated.timing(pressScale, {
      toValue: 1,
      duration: 150,
      useNativeDriver: true,
    }).start();
  }, [pressScale]);

  return (
    <Pressable
      onPress={handlePress}
      onLongPress={handleLongPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      accessibilityRole="button"
      accessibilityLabel={`${title}${isUnread ? ", unread" : ""}${preview ? `, ${preview}` : ""}`}
    >
      <Animated.View style={[styles.row, isSelected && styles.rowSelected, { transform: [{ scale: pressScale }] }]}>
        {isUnread ? (
          <View style={styles.unreadDot} />
        ) : (
          <View style={styles.unreadDotSpacer} />
        )}
        <View style={styles.avatarContainer}>
          {image_url ? (
            <Image
              source={{ uri: buildImageUrl(image_url) }}
              style={styles.avatarImage}
              contentFit="cover"
              transition={200}
            />
          ) : image_status === "generating" ? (
            <GeneratingAvatar />
          ) : image_status === "failed" ? (
            <View style={[styles.avatar, styles.avatarFailed]}>
              <Text style={styles.avatarGeneratingText}>⚠️</Text>
            </View>
          ) : (
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{initials || "?"}</Text>
            </View>
          )}
          {status === "active" && (
            <View style={[styles.statusDot, { backgroundColor: STATUS_COLORS.active }]} />
          )}
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
          {preview ? (
            <View style={is_thinking ? styles.previewWithThinking : undefined}>
              <Text style={[styles.preview, isUnread && styles.previewUnread]}>
                {preview}
              </Text>
              {is_thinking && <TypingDots />}
            </View>
          ) : is_thinking ? (
            <TypingDots />
          ) : (
            <Text style={styles.emptyPreview}>No messages yet</Text>
          )}
        </View>
      </Animated.View>
    </Pressable>
  );
});

/** Pulsing sparkle avatar shown while cover image is generating.
 *  Respects reduce-motion preference — shows static avatar instead. */
function GeneratingAvatar() {
  const reduceMotion = useReduceMotion();
  const pulse = useRef(new Animated.Value(reduceMotion ? 0.7 : 0.4)).current;

  useEffect(() => {
    if (reduceMotion) {
      pulse.setValue(0.7);
      return;
    }
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 800, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.4, duration: 800, useNativeDriver: true }),
      ]),
    );
    anim.start();
    return () => anim.stop();
  }, [pulse, reduceMotion]);

  return (
    <Animated.View style={[styles.avatar, styles.avatarGenerating, { opacity: pulse }]}>
      <Text style={styles.avatarGeneratingText}>✨</Text>
    </Animated.View>
  );
}

/** Small pulsing dots for typing indicator in chat list */
function TypingDots() {
  return (
    <View style={styles.typingRow}>
      <PulsingDots size={6} gap={4} />
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
    backgroundColor: "#1f1f23",
  },
  rowSelected: {
    backgroundColor: "#1e293b",
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
  avatarImage: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#3f3f46",
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
  avatarGenerating: {
    backgroundColor: "#2d2640",
    borderWidth: 1,
    borderColor: "#7c3aed",
  },
  avatarFailed: {
    backgroundColor: "#2d1f1f",
    borderWidth: 1,
    borderColor: "#991b1b",
  },
  avatarGeneratingText: {
    fontSize: 18,
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
  previewWithThinking: {
    gap: 2,
  },
  typingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    height: 14,
  },
});
