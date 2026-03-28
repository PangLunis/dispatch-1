import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Animated, Platform, Pressable, Share, StyleSheet, Text, type TextLayoutEventData, type NativeSyntheticEvent, View } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import * as Clipboard from "expo-clipboard";
import * as FileSystem from "expo-file-system/legacy";
import * as WebBrowser from "expo-web-browser";
import type { BubbleMenuItem } from "./BubbleMenu";
import type { DisplayMessage } from "../hooks/useMessages";
import { branding } from "../config/branding";
import { buildImageUrl, buildVideoUrl } from "../api/images";
import { relativeTime } from "../utils/time";
import { PulsingDots } from "./PulsingDots";
import { SimpleMarkdown } from "./SimpleMarkdown";

const URL_REGEX = /https?:\/\/[^\s<>\"'\])},]+/gi;

// Horizontal padding inside the bubble (must match styles.bubble.paddingHorizontal)
const BUBBLE_PADDING_H = 12;
// Extra width buffer for rounding, borders, and inline formatting
const BUBBLE_WIDTH_BUFFER = 4;


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
  onTextLayout,
}: {
  text: string;
  style: any;
  linkColor: string;
  onTextLayout?: (e: NativeSyntheticEvent<TextLayoutEventData>) => void;
}) {
  const segments = parseLinks(text);
  if (segments.length === 1 && segments[0].type === "text") {
    return <Text style={style} onTextLayout={onTextLayout}>{text}</Text>;
  }
  return (
    <Text style={style} onTextLayout={onTextLayout}>
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
  onLongPress?: (items: BubbleMenuItem[], pageY: number) => void;
  /** Show "Delivered" indicator under this message */
  showDelivered?: boolean;
}

export function MessageBubble({ message, audioState, onRetry, onLongPress, showDelivered }: MessageBubbleProps) {
  const { role, content, timestamp, isPending, sendFailed, audioUrl, imageUrl, videoUrl, localImageUri, status } = message;
  const isUser = role === "user";
  const isGenerating = status === "generating";
  const isFailed = status === "failed";
  const router = useRouter();

  // Entry animation for user bubbles — slide up + fade in
  const entryAnim = useRef(new Animated.Value(isUser ? 0 : 1)).current;
  const hasAnimated = useRef(!isUser);
  useEffect(() => {
    if (!hasAnimated.current) {
      hasAnimated.current = true;
      Animated.spring(entryAnim, {
        toValue: 1,
        tension: 200,
        friction: 18,
        useNativeDriver: true,
      }).start();
    }
  }, [entryAnim]);

  // Delivered indicator animation — fade in
  const deliveredAnim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (showDelivered) {
      Animated.timing(deliveredAnim, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }).start();
    }
  }, [showDelivered, deliveredAnim]);

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

  // -- Shrink-wrap: measure text line widths to compute tightest bubble width --
  // Only shrink-wraps single-line text-only messages. Multi-line → 80% width.
  const hasMedia = !!(imageUrl || videoUrl || localImageUri || audioUrl);
  const [measuredBubbleWidth, setMeasuredBubbleWidth] = useState<number | undefined>(undefined);
  const [isMultiLine, setIsMultiLine] = useState(false);
  const maxLineWidthRef = useRef(0);
  const totalLineCountRef = useRef(0);
  // Reset measurement when content changes
  const prevContentRef = useRef(content);
  if (prevContentRef.current !== content) {
    prevContentRef.current = content;
    maxLineWidthRef.current = 0;
    totalLineCountRef.current = 0;
    setMeasuredBubbleWidth(undefined);
    setIsMultiLine(false);
  }

  /** Called by text components (LinkedText / SimpleMarkdown) with the max line
   *  width from each text block. We track the overall max across all blocks,
   *  and only shrink-wrap if the total rendered line count is 1. */
  const handleMaxLineWidth = useCallback((lineWidth: number, lineCount?: number) => {
    if (hasMedia) return; // Don't shrink-wrap media messages
    if (lineWidth > maxLineWidthRef.current) {
      maxLineWidthRef.current = lineWidth;
    }
    if (lineCount !== undefined) {
      totalLineCountRef.current += lineCount;
    }
    if (totalLineCountRef.current > 1) {
      setIsMultiLine(true);
      setMeasuredBubbleWidth(undefined);
      return;
    }
    const newWidth = Math.ceil(maxLineWidthRef.current) + BUBBLE_PADDING_H * 2 + BUBBLE_WIDTH_BUFFER;
    if (measuredBubbleWidth === undefined || Math.abs(newWidth - measuredBubbleWidth) > 2) {
      setMeasuredBubbleWidth(newWidth);
    }
  }, [hasMedia, measuredBubbleWidth]);

  /** onTextLayout handler for user messages (LinkedText) */
  const handleUserTextLayout = useCallback((e: NativeSyntheticEvent<TextLayoutEventData>) => {
    if (hasMedia) return;
    const lines = e.nativeEvent.lines;
    if (lines.length === 0) return;
    let max = 0;
    for (const line of lines) {
      if (line.width > max) max = line.width;
    }
    handleMaxLineWidth(max, lines.length);
  }, [hasMedia, handleMaxLineWidth]);

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

  const handleBubbleLongPress = useCallback((e: { nativeEvent: { pageY: number } }) => {
    if (!onLongPress) return;
    const items: BubbleMenuItem[] = [];

    // Copy is always available if there's text
    if (content) {
      items.push({
        label: "Copy",
        icon: "doc.on.doc",
        onPress: () => Clipboard.setStringAsync(content),
      });
    }

    // Play/Pause for assistant messages
    if (canPlayAudio) {
      if (isPlayingThis) {
        items.push({
          label: "Pause",
          icon: "pause.fill",
          onPress: () => audioState?.pause(),
        });
      } else {
        items.push({
          label: "Play",
          icon: "play.fill",
          onPress: handleAudioPress,
        });
      }
    }

    // Save image
    if (imageSource && !isUser && !isPending) {
      items.push({
        label: "Save Image",
        icon: "square.and.arrow.down",
        onPress: handleSaveImage,
      });
    }

    if (items.length > 0) {
      onLongPress(items, e.nativeEvent.pageY);
    }
  }, [content, canPlayAudio, isPlayingThis, audioState, imageSource, isUser, isPending, handleSaveImage, onLongPress, handleAudioPress]);

  return (
    <Animated.View
      style={[
        styles.wrapper,
        isUser ? styles.wrapperUser : styles.wrapperAssistant,
        isUser && {
          opacity: entryAnim,
          transform: [{
            translateY: entryAnim.interpolate({
              inputRange: [0, 1],
              outputRange: [20, 0],
            }),
          }],
        },
      ]}
    >
      <View style={[
        styles.bubbleRow,
        isUser && styles.bubbleRowUser,
        // Audio messages: force full width so waveform is consistent across messages
        !!audioUrl && styles.bubbleRowFullWidth,
        // Multi-line text: 80% width. Single-line: shrink-wrap to measured width.
        !hasMedia && isMultiLine && styles.bubbleRowMultiLine,
        !hasMedia && !isMultiLine && measuredBubbleWidth !== undefined && { width: measuredBubbleWidth, maxWidth: isUser ? "75%" : "90%" },
      ]}>
        {sendFailed && (
          <Pressable
            onPress={() => onRetry?.(message.id)}
            hitSlop={8}
            style={styles.failedIconInline}
          >
            <View style={styles.failedIcon}>
              <Text style={styles.failedIconText}>!</Text>
            </View>
          </Pressable>
        )}
        <Pressable
          onPress={() => setShowTimestamp((v) => !v)}
          onLongPress={(e) => handleBubbleLongPress({ nativeEvent: { pageY: e.nativeEvent.pageY } })}
          delayLongPress={400}
          style={[
            styles.bubble,
            isUser ? styles.bubbleUser : styles.bubbleAssistant,
            // Multi-line text or audio: expand bubble to fill row width
            (!hasMedia && isMultiLine) && styles.bubbleFullWidth,
            !!audioUrl && styles.bubbleFullWidth,
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
                onTextLayout={handleUserTextLayout}
              />
            ) : (
              <SimpleMarkdown onMaxLineWidth={handleMaxLineWidth}>{displayText}</SimpleMarkdown>
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
          {/* Inline audio player for uploaded audio (user or assistant) */}
          {audioUrl && audioState ? (
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
                {[0.3, 0.6, 1, 0.7, 0.4, 0.8, 0.5, 0.9, 0.6, 0.3, 0.7, 0.5, 0.8, 0.4, 0.9, 0.6, 0.3, 0.7, 0.5, 1, 0.6, 0.4, 0.8, 0.3].map((h, i) => (
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
        {/* Side buttons removed — actions now in long-press context menu */}
      </View>
      {showDelivered && !sendFailed && (
        <Animated.Text style={[styles.deliveredText, { opacity: deliveredAnim }]}>Delivered</Animated.Text>
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
    maxWidth: "90%",
  },
  bubbleRowUser: {
    flexDirection: "row-reverse",
    maxWidth: "75%",
  },
  bubbleRowMultiLine: {
    width: "80%",
  },
  bubbleRowFullWidth: {
    width: "90%",
  },
  bubble: {
    flexShrink: 1,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 18,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "transparent", // Prevents layout shift when bubblePlaying adds border
  },
  imageContainer: {
    marginHorizontal: -12,
    marginTop: -7,
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
  },
  bubbleFullWidth: {
    flexGrow: 1,
  },
  bubbleGenerationFailed: {
    borderLeftWidth: 2,
    borderLeftColor: "#ef4444",
  },
  failedIconInline: {
    alignSelf: "center",
  },
  failedIcon: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: "#ef4444",
    alignItems: "center",
    justifyContent: "center",
  },
  failedIconText: {
    color: "#ffffff",
    fontSize: 13,
    fontWeight: "700",
    marginTop: -1,
  },
  deliveredText: {
    color: "#71717a",
    fontSize: 11,
    fontWeight: "400",
    textAlign: "right",
    marginTop: 2,
    marginRight: 4,
  },
  bubblePlaying: {
    borderWidth: 1,
    borderColor: branding.accentColor,
  },
  inlineAudioPlayer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingTop: 8,
    alignSelf: "stretch",
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
    flex: 1,
    maxWidth: 4,
    minWidth: 2,
    borderRadius: 1.5,
    backgroundColor: "rgba(255, 255, 255, 0.5)",
  },
  inlineAudioLabel: {
    color: "rgba(255, 255, 255, 0.6)",
    fontSize: 12,
    fontWeight: "500",
  },
  text: {
    fontSize: 17,
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
