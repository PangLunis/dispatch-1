import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, Share, StyleSheet, Text, View } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import * as FileSystem from "expo-file-system/legacy";
import type { DisplayMessage } from "../hooks/useMessages";
import { branding } from "../config/branding";
import { buildImageUrl } from "../api/images";
import { relativeTime } from "../utils/time";

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
}

export function MessageBubble({ message, audioState, onRetry }: MessageBubbleProps) {
  const { role, content, timestamp, isPending, sendFailed, audioUrl, imageUrl, localImageUri } = message;
  const isUser = role === "user";
  const router = useRouter();

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
    <View
      style={[
        styles.wrapper,
        isUser ? styles.wrapperUser : styles.wrapperAssistant,
      ]}
    >
      <View style={[styles.bubbleRow, isUser && styles.bubbleRowUser]}>
        <Pressable
          onPress={() => setShowTimestamp((v) => !v)}
          style={[
            styles.bubble,
            isUser ? styles.bubbleUser : styles.bubbleAssistant,
            isPending && styles.bubblePending,
            sendFailed && styles.bubbleFailed,
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
          <Text
            style={[
              styles.text,
              isUser ? styles.textUser : styles.textAssistant,
            ]}
            selectable
          >
            {displayText}
          </Text>
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
    </View>
  );
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
  },
  bubblePending: {
    opacity: 0.55,
  },
  bubbleFailed: {
    opacity: 0.7,
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
