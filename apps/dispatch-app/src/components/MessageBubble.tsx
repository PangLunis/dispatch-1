import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Animated, Pressable, Share, StyleSheet, Text, View } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import * as FileSystem from "expo-file-system/legacy";
import * as WebBrowser from "expo-web-browser";
import Markdown from "@ronradtke/react-native-markdown-display";
import type { DisplayMessage } from "../hooks/useMessages";
import { branding } from "../config/branding";
import { buildImageUrl } from "../api/images";
import { relativeTime } from "../utils/time";
import { PulsingDots } from "./PulsingDots";

const URL_REGEX = /https?:\/\/[^\s<>\"'\])},]+/gi;

/**
 * Convert bare URLs in text to markdown links [url](url).
 * Skips URLs already inside markdown link syntax [text](url) or <url>.
 */
function autoLinkUrls(text: string): string {
  // Match bare URLs that aren't already inside markdown link parens or angle brackets
  return text.replace(
    /(?<!\]\()(?<!\<)https?:\/\/[^\s<>\"'\])},]+/gi,
    (url) => {
      // Strip trailing punctuation that's likely not part of the URL
      let cleanUrl = url;
      const trailingPunct = /[.,:;!?)]+$/.exec(cleanUrl);
      let suffix = "";
      if (trailingPunct) {
        suffix = trailingPunct[0];
        cleanUrl = cleanUrl.slice(0, -suffix.length);
      }
      return `[${cleanUrl}](${cleanUrl})${suffix}`;
    },
  );
}

/** Parse text into segments of plain text and URLs */
function parseLinks(text: string): Array<{ type: "text" | "link"; value: string }> {
  const segments: Array<{ type: "text" | "link"; value: string }> = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  URL_REGEX.lastIndex = 0;
  while ((match = URL_REGEX.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    // Strip trailing punctuation that's likely not part of the URL
    let url = match[0];
    const trailingPunct = /[.,:;!?)]+$/.exec(url);
    if (trailingPunct) {
      url = url.slice(0, -trailingPunct[0].length);
    }
    segments.push({ type: "link", value: url });
    lastIndex = match.index + url.length;
    // Adjust regex position if we trimmed trailing chars
    URL_REGEX.lastIndex = lastIndex;
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", value: text.slice(lastIndex) });
  }
  return segments;
}

/** Render text with clickable links */
function LinkedText({
  text,
  style,
  linkColor,
}: {
  text: string;
  style: any;
  linkColor: string;
}) {
  const segments = parseLinks(text);
  if (segments.length === 1 && segments[0].type === "text") {
    return <Text style={style}>{text}</Text>;
  }
  return (
    <Text style={style}>
      {segments.map((seg, i) =>
        seg.type === "link" ? (
          <Text
            key={i}
            style={{ textDecorationLine: "underline", color: linkColor }}
            onPress={() => WebBrowser.openBrowserAsync(seg.value)}
          >
            {seg.value}
          </Text>
        ) : (
          seg.value
        ),
      )}
    </Text>
  );
}

const MAX_COLLAPSED_LENGTH = 840;

interface MessageBubbleProps {
  message: DisplayMessage;
  audioState?: {
    isPlaying: boolean;
    isPaused: boolean;
    currentMessageId: string | null;
    play: (messageId: string, audioUrl: string) => Promise<void>;
    pause: () => void;
    resume: () => void;
  };
  onRetry?: (messageId: string) => void;
  onLongPress?: (message: DisplayMessage, pageY: number) => void;
}

export function MessageBubble({ message, audioState, onRetry, onLongPress }: MessageBubbleProps) {
  const { role, content, timestamp, isPending, sendFailed, audioUrl, imageUrl, localImageUri, status } = message;
  const isUser = role === "user";
  const isGenerating = status === "generating";
  const isFailed = status === "failed";
  const router = useRouter();

  // Animated opacity for pending → delivered transition
  const opacityAnim = useRef(new Animated.Value(isPending ? 0.55 : 1)).current;
  const prevPendingRef = useRef(isPending);

  useEffect(() => {
    if (prevPendingRef.current && !isPending && !sendFailed) {
      // Smoothly animate from pending opacity to full
      Animated.timing(opacityAnim, { toValue: 1, duration: 300, useNativeDriver: true }).start();
    } else if (sendFailed) {
      Animated.timing(opacityAnim, { toValue: 0.7, duration: 200, useNativeDriver: true }).start();
    }
    prevPendingRef.current = isPending;
  }, [isPending, sendFailed, opacityAnim]);

  // Determine image source: optimistic local preview takes priority over server URL
  const imageSource = localImageUri
    ? { uri: localImageUri }
    : imageUrl
      ? { uri: buildImageUrl(imageUrl) }
      : null;
  const [expanded, setExpanded] = useState(false);
  const [showTimestamp, setShowTimestamp] = useState(false);
  const [isGeneratingAudio, setIsGeneratingAudio] = useState(false);
  const [isSavingImage, setIsSavingImage] = useState(false);

  const handleSaveImage = useCallback(async () => {
    if (!imageSource) return;
    setIsSavingImage(true);
    try {
      let localUri = imageSource.uri;
      if (localUri.startsWith("http")) {
        const filename = `image_${Date.now()}.jpeg`;
        const downloadResult = await FileSystem.downloadAsync(
          localUri,
          FileSystem.cacheDirectory + filename,
        );
        localUri = downloadResult.uri;
      }
      // Try native save, fall back to share sheet
      try {
        const MediaLibrary = await import("expo-media-library");
        const { status } = await MediaLibrary.requestPermissionsAsync();
        if (status !== "granted") {
          Alert.alert("Permission needed", "Please allow access to save photos.");
          return;
        }
        await MediaLibrary.saveToLibraryAsync(localUri);
        Alert.alert("Saved", "Image saved to Photos.");
      } catch {
        await Share.share({ url: localUri, message: imageSource.uri });
      }
    } catch {
      Alert.alert("Error", "Failed to save image.");
    } finally {
      setIsSavingImage(false);
    }
  }, [imageSource]);

  const isLong = (content || "").length > MAX_COLLAPSED_LENGTH;
  const displayText =
    isLong && !expanded
      ? (content || "").slice(0, MAX_COLLAPSED_LENGTH) + "..."
      : content || "";

  const isCurrentMessage = audioState?.currentMessageId === message.id;
  const isPlayingThis = isCurrentMessage && audioState?.isPlaying;
  const isPausedThis = isCurrentMessage && audioState?.isPaused;
  // Show play button on assistant messages only when audioState is provided
  const canPlayAudio = !isUser && !isPending && !!audioState;

  const handleAudioPress = async () => {
    if (!audioState) return;

    if (isPlayingThis) {
      audioState.pause();
      return;
    }
    if (isPausedThis) {
      audioState.resume();
      return;
    }

    // Build audio path (lazy TTS — server generates on first request)
    // downloadAudio in audio.ts handles prepending API_BASE_URL and adding token
    const url = audioUrl || `/audio/${message.id}`;

    setIsGeneratingAudio(true);
    try {
      await audioState.play(message.id, url);
    } catch {
      // Audio generation/playback failed — silently handle
    } finally {
      setIsGeneratingAudio(false);
    }
  };

  return (
    <Animated.View
      style={[
        styles.wrapper,
        isUser ? styles.wrapperUser : styles.wrapperAssistant,
        (isPending || sendFailed) ? { opacity: opacityAnim } : undefined,
      ]}
    >
      <View style={[styles.bubbleRow, isUser && styles.bubbleRowUser]}>
        <Pressable
          onPress={() => setShowTimestamp((v) => !v)}
          onLongPress={(e) => {
            onLongPress?.(message, e.nativeEvent.pageY);
          }}
          delayLongPress={400}
          style={[
            styles.bubble,
            isUser ? styles.bubbleUser : styles.bubbleAssistant,
            isFailed && styles.bubbleGenerationFailed,
            isPlayingThis && styles.bubblePlaying,
          ]}
        >
          {imageSource && (
            <Pressable
              style={styles.imageContainer}
              onPress={() => {
                router.push({
                  pathname: "/image-viewer",
                  params: { uri: imageSource.uri },
                });
              }}
            >
              <Image
                source={imageSource}
                style={styles.inlineImage}
                contentFit="cover"
                transition={200}
              />
            </Pressable>
          )}
          {isGenerating ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <GeneratingDots />
              <Text style={[styles.text, { color: "#a1a1aa" }]}>Generating image…</Text>
            </View>
          ) : isUser ? (
            <LinkedText
              text={displayText}
              style={[styles.text, styles.textUser]}
              linkColor="#d4e8ff"
            />
          ) : (
            <Markdown style={markdownStyles} onLinkPress={(url) => { WebBrowser.openBrowserAsync(url); return false; }}>
              {autoLinkUrls(displayText)}
            </Markdown>
          )}
          {isLong && (
            <Pressable
              onPress={() => setExpanded((v) => !v)}
              hitSlop={8}
            >
              <Text style={styles.expandToggle}>
                {expanded ? "Show less" : "Show more"}
              </Text>
            </Pressable>
          )}
        </Pressable>
        {/* Side action buttons — stacked vertically so save sits above play */}
        {(imageSource && !isUser && !isPending) || canPlayAudio ? (
          <View style={styles.sideButtons}>
            {imageSource && !isUser && !isPending && (
              <Pressable
                onPress={handleSaveImage}
                hitSlop={8}
                style={styles.audioButton}
                disabled={isSavingImage}
              >
                {isSavingImage ? (
                  <ActivityIndicator size={14} color="#71717a" />
                ) : (
                  <SaveIcon />
                )}
              </Pressable>
            )}
            {canPlayAudio && (
              <Pressable
                onPress={handleAudioPress}
                hitSlop={8}
                style={styles.audioButton}
                disabled={isGeneratingAudio}
              >
                {isGeneratingAudio ? (
                  <ActivityIndicator size={14} color="#71717a" />
                ) : isPlayingThis ? (
                  <PauseIcon />
                ) : (
                  <PlayIcon />
                )}
              </Pressable>
            )}
          </View>
        ) : null}
      </View>
      {sendFailed && (
        <Pressable
          onPress={() => onRetry?.(message.id)}
          style={styles.failedRow}
          hitSlop={8}
        >
          <View style={styles.failedIcon}>
            <Text style={styles.failedIconText}>!</Text>
          </View>
          <Text style={styles.failedText}>Not Delivered</Text>
        </Pressable>
      )}
      {showTimestamp && (
        <Text
          style={[
            styles.timestamp,
            isUser ? styles.timestampUser : styles.timestampAssistant,
          ]}
        >
          {relativeTime(timestamp)}
        </Text>
      )}
    </Animated.View>
  );
}

/** Pulsing dots for "generating" state */
function GeneratingDots() {
  return <PulsingDots color="#a78bfa" size={6} gap={4} />;
}

/** Play triangle icon drawn with RN Views */
function PlayIcon() {
  return (
    <View style={iconStyles.playContainer}>
      <View style={iconStyles.playTriangle} />
    </View>
  );
}

/** Download/save icon */
function SaveIcon() {
  return (
    <View style={iconStyles.saveContainer}>
      <View style={iconStyles.saveArrow} />
      <View style={iconStyles.saveTray} />
    </View>
  );
}

/** Pause icon (two vertical bars) drawn with RN Views */
function PauseIcon() {
  return (
    <View style={iconStyles.pauseContainer}>
      <View style={iconStyles.pauseBar} />
      <View style={iconStyles.pauseBar} />
    </View>
  );
}

const iconStyles = StyleSheet.create({
  playContainer: {
    width: 14,
    height: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  playTriangle: {
    width: 0,
    height: 0,
    borderLeftWidth: 10,
    borderTopWidth: 6,
    borderBottomWidth: 6,
    borderLeftColor: "#71717a",
    borderTopColor: "transparent",
    borderBottomColor: "transparent",
    marginLeft: 2,
  },
  pauseContainer: {
    width: 14,
    height: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
  },
  pauseBar: {
    width: 3,
    height: 11,
    backgroundColor: "#71717a",
    borderRadius: 1,
  },
  saveContainer: {
    width: 14,
    height: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  saveArrow: {
    width: 0,
    height: 0,
    borderLeftWidth: 5,
    borderRightWidth: 5,
    borderTopWidth: 6,
    borderLeftColor: "transparent",
    borderRightColor: "transparent",
    borderTopColor: "#71717a",
    marginBottom: 1,
  },
  saveTray: {
    width: 12,
    height: 1.5,
    backgroundColor: "#71717a",
    borderRadius: 1,
  },
});

/** Markdown styles for assistant message bubbles — matches dark theme */
const markdownStyles = StyleSheet.create({
  body: {
    color: "#fafafa",
    fontSize: 16,
    lineHeight: 22,
  },
  heading1: {
    color: "#fafafa",
    fontSize: 20,
    fontWeight: "700",
    marginTop: 8,
    marginBottom: 4,
  },
  heading2: {
    color: "#fafafa",
    fontSize: 18,
    fontWeight: "700",
    marginTop: 6,
    marginBottom: 4,
  },
  heading3: {
    color: "#fafafa",
    fontSize: 16,
    fontWeight: "700",
    marginTop: 4,
    marginBottom: 2,
  },
  strong: {
    fontWeight: "700",
    color: "#fafafa",
  },
  em: {
    fontStyle: "italic",
    color: "#fafafa",
  },
  link: {
    color: branding.accentColor,
    textDecorationLine: "underline",
  },
  blockquote: {
    backgroundColor: "#1e1e22",
    borderLeftWidth: 3,
    borderLeftColor: "#52525b",
    paddingLeft: 10,
    paddingVertical: 4,
    marginVertical: 4,
  },
  code_inline: {
    backgroundColor: "#1e1e22",
    color: "#e4e4e7",
    fontFamily: "SpaceMono",
    fontSize: 14,
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderRadius: 4,
  },
  code_block: {
    backgroundColor: "#1e1e22",
    color: "#e4e4e7",
    fontFamily: "SpaceMono",
    fontSize: 13,
    lineHeight: 18,
    padding: 10,
    borderRadius: 8,
    marginVertical: 4,
  },
  fence: {
    backgroundColor: "#1e1e22",
    color: "#e4e4e7",
    fontFamily: "SpaceMono",
    fontSize: 13,
    lineHeight: 18,
    padding: 10,
    borderRadius: 8,
    marginVertical: 4,
  },
  list_item: {
    color: "#fafafa",
    fontSize: 16,
    lineHeight: 22,
    marginVertical: 2,
  },
  bullet_list: {
    marginVertical: 4,
  },
  ordered_list: {
    marginVertical: 4,
  },
  hr: {
    backgroundColor: "#3f3f46",
    height: 1,
    marginVertical: 8,
  },
  paragraph: {
    marginTop: 0,
    marginBottom: 4,
  },
  // Remove extra margins on the last paragraph
  textgroup: {
    color: "#fafafa",
  },
});

const styles = StyleSheet.create({
  wrapper: {
    paddingHorizontal: 12,
    marginVertical: 3,
  },
  wrapperUser: {
    alignItems: "flex-end",
  },
  wrapperAssistant: {
    alignItems: "flex-start",
  },
  bubbleRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 6,
    maxWidth: "85%",
  },
  bubbleRowUser: {
    flexDirection: "row-reverse",
  },
  bubble: {
    flexShrink: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "transparent", // Prevents layout shift when bubblePlaying adds border
  },
  imageContainer: {
    marginHorizontal: -14,
    marginTop: -10,
    marginBottom: 8,
  },
  inlineImage: {
    width: "100%",
    aspectRatio: 4 / 3,
    backgroundColor: "#3f3f46",
  },
  bubbleUser: {
    backgroundColor: branding.accentColor,
    borderBottomRightRadius: 4,
  },
  bubbleAssistant: {
    backgroundColor: "#27272a",
    borderBottomLeftRadius: 4,
    flexGrow: 1,
  },
  bubbleGenerationFailed: {
    borderLeftWidth: 2,
    borderLeftColor: "#ef4444",
  },
  failedRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginTop: 4,
    alignSelf: "flex-end",
  },
  failedIcon: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: "#ef4444",
    alignItems: "center",
    justifyContent: "center",
  },
  failedIconText: {
    color: "#ffffff",
    fontSize: 12,
    fontWeight: "700",
    marginTop: -1,
  },
  failedText: {
    color: "#ef4444",
    fontSize: 12,
    fontWeight: "500",
  },
  bubblePlaying: {
    borderWidth: 1,
    borderColor: branding.accentColor,
  },
  text: {
    fontSize: 16,
    lineHeight: 22,
  },
  textUser: {
    color: "#ffffff",
  },
  textAssistant: {
    color: "#fafafa",
  },
  expandToggle: {
    color: "#a1a1aa",
    fontSize: 13,
    fontWeight: "600",
    marginTop: 6,
  },
  sideButtons: {
    flexDirection: "column",
    justifyContent: "flex-end",
    gap: 4,
  },
  audioButton: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "#27272a",
    alignItems: "center",
    justifyContent: "center",
  },
  timestamp: {
    color: "#71717a",
    fontSize: 11,
    marginTop: 2,
    marginHorizontal: 4,
  },
  timestampUser: {
    textAlign: "right",
  },
  timestampAssistant: {
    textAlign: "left",
  },
});
