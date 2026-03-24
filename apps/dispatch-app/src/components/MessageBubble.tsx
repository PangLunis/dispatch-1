import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Animated, Pressable, Share, StyleSheet, Text, View } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import * as FileSystem from "expo-file-system/legacy";
import * as WebBrowser from "expo-web-browser";
import type { DisplayMessage } from "../hooks/useMessages";
import { branding } from "../config/branding";
import { buildImageUrl, buildVideoUrl } from "../api/images";
import { relativeTime } from "../utils/time";
import { PulsingDots } from "./PulsingDots";
import { SimpleMarkdown } from "./SimpleMarkdown";

const URL_REGEX = /https?:\/\/[^\s<>\"'\])},]+/gi;


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
  const { role, content, timestamp, isPending, sendFailed, audioUrl, imageUrl, videoUrl, localImageUri, status } = message;
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

  // Detect if the local attachment is a video by extension
  const videoExts = [".mp4", ".mov", ".m4v", ".avi", ".mkv"];
  const isLocalVideo = localImageUri
    ? videoExts.some((ext) => localImageUri.toLowerCase().endsWith(ext))
    : false;

  // Determine image source: optimistic local preview takes priority over server URL
  // But skip if it's actually a video file (Image component can't render video)
  const imageSource = localImageUri && !isLocalVideo
    ? { uri: localImageUri }
    : imageUrl
      ? { uri: buildImageUrl(imageUrl) }
      : null;

  // Video source: server URL takes priority, fall back to local video URI for optimistic preview
  const videoSource = videoUrl
    ? buildVideoUrl(videoUrl)
    : isLocalVideo
      ? localImageUri
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
    } catch (err) {
      console.warn("[MessageBubble] Audio playback failed:", (err as Error)?.message || err);
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
            (imageSource || videoSource) && !displayText && styles.bubbleMediaOnly,
          ]}
        >
          {videoSource ? (
            <Pressable
              style={displayText ? [styles.imageContainer, styles.imageContainerWithText] : undefined}
              onPress={() => {
                router.push({
                  pathname: "/video-player",
                  params: { uri: videoSource },
                });
              }}
            >
              <View style={styles.videoThumbnail}>
                <View style={styles.videoPlayCircle}>
                  <View style={styles.videoPlayTriangle} />
                </View>
                <Text style={styles.videoLabel}>Video</Text>
              </View>
            </Pressable>
          ) : imageSource ? (
            <Pressable
              style={displayText ? [styles.imageContainer, styles.imageContainerWithText] : undefined}
              onPress={() => {
                router.push({
                  pathname: "/image-viewer",
                  params: { uri: imageSource.uri },
                });
              }}
            >
              <Image
                source={imageSource}
                style={[styles.inlineImage, !displayText && styles.inlineImageRounded]}
                contentFit="cover"
                transition={200}
              />
            </Pressable>
          ) : null}
          {isGenerating ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <GeneratingDots />
              <Text style={[styles.text, { color: "#a1a1aa" }]}>Generating image…</Text>
            </View>
          ) : displayText ? (
            isUser ? (
              <LinkedText
                text={displayText}
                style={[styles.text, styles.textUser]}
                linkColor="#d4e8ff"
              />
            ) : (
              <SimpleMarkdown>{displayText}</SimpleMarkdown>
            )
          ) : null}
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
          {/* Inline audio player for user-uploaded audio */}
          {isUser && audioUrl && audioState ? (
            <Pressable
              onPress={handleAudioPress}
              style={styles.inlineAudioPlayer}
            >
              <View style={styles.inlineAudioPlayBtn}>
                {isPlayingThis ? (
                  <View style={styles.inlineAudioPauseIcon}>
                    <View style={styles.inlineAudioPauseBar} />
                    <View style={styles.inlineAudioPauseBar} />
                  </View>
                ) : isGeneratingAudio ? (
                  <ActivityIndicator size={14} color="#ffffff" />
                ) : (
                  <View style={styles.inlineAudioPlayIcon} />
                )}
              </View>
              <View style={styles.inlineAudioWaveform}>
                {[0.3, 0.6, 1, 0.7, 0.4, 0.8, 0.5, 0.9, 0.6, 0.3, 0.7, 0.5].map((h, i) => (
                  <View
                    key={i}
                    style={[
                      styles.inlineAudioBar,
                      { height: h * 24 },
                      isPlayingThis && { backgroundColor: "#ffffff" },
                    ]}
                  />
                ))}
              </View>
              <Text style={styles.inlineAudioLabel}>Audio</Text>
            </Pressable>
          ) : null}
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
  },
  imageContainerWithText: {
    marginBottom: 8,
  },
  inlineImage: {
    width: "100%",
    aspectRatio: 4 / 3,
    backgroundColor: "#3f3f46",
  },
  inlineImageRounded: {
    borderRadius: 18,
  },
  bubbleMediaOnly: {
    backgroundColor: "transparent",
    paddingHorizontal: 0,
    paddingVertical: 0,
    borderWidth: 0,
  },
  videoThumbnail: {
    width: "100%",
    aspectRatio: 16 / 9,
    backgroundColor: "#18181b",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  videoPlayCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: "rgba(255, 255, 255, 0.15)",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "rgba(255, 255, 255, 0.3)",
  },
  videoPlayTriangle: {
    width: 0,
    height: 0,
    borderLeftWidth: 20,
    borderTopWidth: 12,
    borderBottomWidth: 12,
    borderLeftColor: "#ffffff",
    borderTopColor: "transparent",
    borderBottomColor: "transparent",
    marginLeft: 4,
  },
  videoLabel: {
    color: "#a1a1aa",
    fontSize: 13,
    fontWeight: "500",
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
  inlineAudioPlayer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingTop: 8,
    minWidth: 180,
  },
  inlineAudioPlayBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(255, 255, 255, 0.2)",
    alignItems: "center",
    justifyContent: "center",
  },
  inlineAudioPlayIcon: {
    width: 0,
    height: 0,
    borderLeftWidth: 12,
    borderTopWidth: 7,
    borderBottomWidth: 7,
    borderLeftColor: "#ffffff",
    borderTopColor: "transparent",
    borderBottomColor: "transparent",
    marginLeft: 2,
  },
  inlineAudioPauseIcon: {
    flexDirection: "row",
    gap: 3,
  },
  inlineAudioPauseBar: {
    width: 3,
    height: 14,
    backgroundColor: "#ffffff",
    borderRadius: 1.5,
  },
  inlineAudioWaveform: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
    flex: 1,
  },
  inlineAudioBar: {
    width: 3,
    borderRadius: 1.5,
    backgroundColor: "rgba(255, 255, 255, 0.5)",
  },
  inlineAudioLabel: {
    color: "rgba(255, 255, 255, 0.6)",
    fontSize: 12,
    fontWeight: "500",
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
