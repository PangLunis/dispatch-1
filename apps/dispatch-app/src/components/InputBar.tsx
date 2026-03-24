import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Animated,
  AppState,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
// Lazy-load DocumentPicker to avoid crash when native module isn't available (e.g. Expo Go)
let DocumentPicker: typeof import("expo-document-picker") | null = null;
try {
  DocumentPicker = require("expo-document-picker");
} catch {
  // Native module not available
}
import * as Clipboard from "expo-clipboard";
import * as FileSystem from "expo-file-system/legacy";
import { SymbolView } from "expo-symbols";
import { branding } from "../config/branding";
import { makeLayoutAnim, safeConfigureNext } from "../utils/animation";
import { impactLight } from "../utils/haptics";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { VoiceStrip } from "./VoiceStrip";
import type { VoiceConversationReturn } from "../hooks/useVoiceConversation";
import { SessionPicker } from "./SessionPicker";
import { SkillPicker } from "./SkillPicker";
import type { AgentSession } from "../api/types";
import type { Skill } from "../api/skills";
import { SESSION_CONTEXT_PROMPT, REVIEW_PROMPT, PLAN_BUILD_TEST_PROMPT } from "../prompts/attachPrompts";

type ActivePanel = "none" | "attach" | "sessions" | "skills";

interface InputBarProps {
  onSend: (text: string) => void;
  onSendWithImage?: (text: string, imageUri: string) => void;
  disabled?: boolean;
  chatId?: string;
  voiceConversation?: VoiceConversationReturn;
  /** Ref that parent sets to a function that clears the text input (used by voice mode). */
  clearTextRef?: React.MutableRefObject<(() => void) | null>;
}

export function InputBar({ onSend, onSendWithImage, disabled, chatId, voiceConversation, clearTextRef }: InputBarProps) {
  const [text, setText] = useState("");
  const [selectedAttachments, setSelectedAttachments] = useState<string[]>([]);
  const [activePanel, setActivePanel] = useState<ActivePanel>("none");
  const speech = useSpeechRecognition();
  const insets = useSafeAreaInsets();

  // Wire up clearTextRef so parent (voice mode) can clear the input
  useEffect(() => {
    if (clearTextRef) {
      clearTextRef.current = () => setText("");
    }
    return () => {
      if (clearTextRef) clearTextRef.current = null;
    };
  }, [clearTextRef]);

  const handleMicLongPress = useCallback(() => {
    if (text.trim()) return; // Ignore long-press when text is present — send text first
    voiceConversation?.activate();
  }, [voiceConversation, text]);

  // Track text that was in the field before dictation started
  const [preDictationText, setPreDictationText] = useState("");
  const [clipboardHasImage, setClipboardHasImage] = useState(false);
  const [isFocused, setIsFocused] = useState(false);

  // Check clipboard for images on focus and app foreground (no polling)
  const checkClipboard = useCallback(async () => {
    if (!onSendWithImage || selectedAttachments.length > 0) return;
    try {
      const hasImage = await Clipboard.hasImageAsync();
      setClipboardHasImage(hasImage);
    } catch {
      setClipboardHasImage(false);
    }
  }, [onSendWithImage, selectedAttachments]);

  useEffect(() => {
    if (!isFocused) {
      setClipboardHasImage(false);
      return;
    }
    checkClipboard();
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active" && isFocused) checkClipboard();
    });
    return () => sub.remove();
  }, [isFocused, checkClipboard]);

  const handlePasteImage = useCallback(async () => {
    try {
      const clipImage = await Clipboard.getImageAsync({ format: "png" });
      if (clipImage && clipImage.data) {
        const filename = `clipboard_${Date.now()}.png`;
        const uri = FileSystem.cacheDirectory + filename;
        await FileSystem.writeAsStringAsync(uri, clipImage.data, {
          encoding: FileSystem.EncodingType.Base64,
        });
        setSelectedAttachments((prev) => [...prev, uri]);
        setClipboardHasImage(false);
        impactLight();
      }
    } catch {
      // Clipboard read failed
    }
  }, []);

  const canSend = !!(text.trim().length > 0 || selectedAttachments.length > 0) && !disabled;
  const showMic = !text.trim() && selectedAttachments.length === 0 && speech.isAvailable && !disabled && !speech.isListening;

  // Send button pop-in animation
  const sendButtonScale = useRef(new Animated.Value(0)).current;
  const prevCanSend = useRef(false);

  useEffect(() => {
    if (canSend && !prevCanSend.current) {
      // Pop in
      sendButtonScale.setValue(0);
      Animated.spring(sendButtonScale, {
        toValue: 1,
        tension: 200,
        friction: 12,
        useNativeDriver: true,
      }).start();
    } else if (!canSend && prevCanSend.current) {
      // Shrink out
      Animated.timing(sendButtonScale, {
        toValue: 0,
        duration: 150,
        useNativeDriver: true,
      }).start();
    }
    prevCanSend.current = canSend;
  }, [canSend, sendButtonScale]);

  // Sync speech transcript into the text field (skip when voice mode is active —
  // the global STT singleton fires events to both hooks, and useSpeechCapture's
  // activeRef guard handles its side; we suppress the old hook's side here)
  useEffect(() => {
    if (voiceConversation?.isActive) return;
    if (!speech.isListening && !speech.transcript && !speech.partialTranscript) return;
    const liveText = speech.partialTranscript || speech.transcript;
    if (liveText) {
      const prefix = preDictationText ? preDictationText + " " : "";
      setText(prefix + liveText);
    }
  }, [speech.transcript, speech.partialTranscript, speech.isListening, preDictationText, voiceConversation?.isActive]);

  const handleSend = useCallback(() => {
    if (!canSend) return;
    impactLight();
    if (speech.isListening) speech.stop();

    if (selectedAttachments.length > 0 && onSendWithImage) {
      // Send first attachment with the text, rest with empty text
      selectedAttachments.forEach((uri, i) => {
        onSendWithImage(i === 0 ? text.trim() : "", uri);
      });
    } else if (text.trim()) {
      onSend(text.trim());
    }

    setText("");
    setSelectedAttachments([]);
    setPreDictationText("");
    speech.reset();
  }, [canSend, onSend, onSendWithImage, text, selectedAttachments, speech]);

  const handleMicPress = useCallback(() => {
    impactLight();
    setPreDictationText(text);
    speech.reset();
    speech.start();
  }, [speech, text]);

  const handleStopDictation = useCallback(() => {
    impactLight();
    speech.stop();
  }, [speech]);

  const handlePickFromGallery = useCallback(async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images", "videos"],
        quality: 0.8,
        allowsEditing: false,
        allowsMultipleSelection: true,
      });
      if (!result.canceled && result.assets.length > 0) {
        setSelectedAttachments((prev) => [...prev, ...result.assets.map((a) => a.uri)]);
      }
    } catch (err) {
      console.error("[InputBar] Gallery error:", err);
      Alert.alert("Gallery Error", "Could not open photo library.");
    }
  }, []);

  const handlePickFromFiles = useCallback(async () => {
    if (!DocumentPicker) {
      Alert.alert("Files Unavailable", "File picker requires a native build. Use Gallery or Camera instead.");
      return;
    }
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: "*/*",
        copyToCacheDirectory: true,
      });
      if (!result.canceled && result.assets && result.assets.length > 0) {
        setSelectedAttachments((prev) => [...prev, ...result.assets!.map((a) => a.uri)]);
      }
    } catch (err) {
      console.error("[InputBar] DocumentPicker error:", err);
      Alert.alert("Files Error", "Could not open file picker. Try Gallery instead.");
    }
  }, []);

  const handleTakePicture = useCallback(async () => {
    try {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== "granted") {
        Alert.alert("Camera Access", "Enable camera access in Settings to take photos.");
        return;
      }
      const result = await ImagePicker.launchCameraAsync({
        quality: 0.8,
        allowsEditing: false,
      });
      if (!result.canceled && result.assets.length > 0) {
        setSelectedAttachments((prev) => [...prev, result.assets[0].uri]);
      }
    } catch (err) {
      console.error("[InputBar] Camera error:", err);
      Alert.alert("Camera Error", "Could not open camera.");
    }
  }, []);

  const handleAttachPress = useCallback(() => {
    impactLight();
    safeConfigureNext(makeLayoutAnim(200));
    setActivePanel((prev) => (prev === "attach" ? "none" : "attach"));
  }, []);

  const handleAttachOption = useCallback(
    (action: () => void) => {
      setActivePanel("none");
      action();
    },
    []
  );

  const handleOpenSessionPicker = useCallback(() => {
    setActivePanel("sessions");
  }, []);

  const handleOpenSkillPicker = useCallback(() => {
    setActivePanel("skills");
  }, []);

  const handleSelectSession = useCallback(
    (session: AgentSession) => {
      setActivePanel("none");
      onSend(SESSION_CONTEXT_PROMPT(session));
    },
    [onSend]
  );

  const handleSelectSkill = useCallback(
    (skill: Skill) => {
      setActivePanel("none");
      const prefix = text.trim() ? text.trim() + " " : "";
      setText(prefix + `/${skill.name} `);
    },
    [text]
  );

  const handleReview = useCallback(() => {
    setActivePanel("none");
    onSend(REVIEW_PROMPT);
  }, [onSend]);

  const handlePlanBuildTest = useCallback(() => {
    setActivePanel("none");
    onSend(PLAN_BUILD_TEST_PROMPT);
  }, [onSend]);

  const handleNudge = useCallback(() => {
    setActivePanel("none");
    onSend("Keep going!");
  }, [onSend]);

  const handleBugFinder = useCallback(() => {
    setActivePanel("none");
    onSend("Use /bug-finder — run in a subagent to find bugs with the above.");
  }, [onSend]);

  const handleRemoveAttachment = useCallback((index: number) => {
    setSelectedAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  return (
    <>
      {clipboardHasImage && selectedAttachments.length === 0 ? (
        <Pressable
          onPress={handlePasteImage}
          style={styles.pasteBar}
          accessibilityRole="button"
          accessibilityLabel="Paste image from clipboard"
        >
          <View style={styles.pasteBarContent}>
            <SymbolView name={{ ios: "doc.on.clipboard", android: "content_paste", web: "content_paste" }} tintColor="#a1a1aa" size={14} />
            <Text style={styles.pasteBarText}>Paste image from clipboard</Text>
          </View>
        </Pressable>
      ) : null}

      {activePanel === "attach" && onSendWithImage ? (
        <View accessibilityRole="toolbar" accessibilityLabel="Attachment options">
          <View style={attachStyles.row}>
            <AttachOption icon="camera.fill" label="Camera" onPress={() => handleAttachOption(handleTakePicture)} />
            <AttachOption icon="photo.fill" label="Gallery" onPress={() => handleAttachOption(handlePickFromGallery)} />
            <AttachOption icon="folder.fill" label="Files" onPress={() => handleAttachOption(handlePickFromFiles)} />
            <AttachOption icon="bubble.left.and.bubble.right.fill" label="Sessions" iconSize={18} onPress={handleOpenSessionPicker} />
            <AttachOption icon="wrench.and.screwdriver.fill" label="Skills" iconColor="#38bdf8" onPress={handleOpenSkillPicker} />
          </View>
          <View style={[attachStyles.row, { borderTopWidth: 0, paddingTop: 0 }]}>
            <AttachOption icon="checkmark.seal.fill" label="Review" iconColor="#a78bfa" onPress={handleReview} />
            <AttachOption icon="hammer.fill" label="Build" iconColor="#f59e0b" onPress={handlePlanBuildTest} />
            <AttachOption icon="ant.fill" label="Debug" iconColor="#ef4444" onPress={handleBugFinder} />
            <AttachOption icon="arrow.right.circle.fill" label="Nudge" iconColor="#34d399" onPress={handleNudge} />
          </View>
        </View>
      ) : null}

      {activePanel === "sessions" ? (
        <SessionPicker
          onSelect={handleSelectSession}
          onClose={() => setActivePanel("none")}
          currentChatId={chatId}
        />
      ) : null}

      {activePanel === "skills" ? (
        <SkillPicker
          onSelect={handleSelectSkill}
          onClose={() => setActivePanel("none")}
        />
      ) : null}

      {selectedAttachments.length > 0 ? (
        <View style={styles.imagePreviewContainer}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {selectedAttachments.map((uri, index) => (
              <View key={`${uri}-${index}`} style={styles.imagePreviewWrapper}>
                <Image
                  source={{ uri }}
                  style={styles.imagePreview}
                  accessibilityLabel={`Selected attachment ${index + 1}`}
                />
                <Pressable
                  onPress={() => handleRemoveAttachment(index)}
                  style={styles.imageRemoveButton}
                  hitSlop={8}
                  accessibilityRole="button"
                  accessibilityLabel={`Remove attachment ${index + 1}`}
                >
                  <SymbolView name={{ ios: "xmark", android: "close", web: "close" }} tintColor="#fafafa" size={10} weight="bold" />
                </Pressable>
              </View>
            ))}
          </ScrollView>
        </View>
      ) : null}

      <View style={[styles.container, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        {voiceConversation?.isActive ? (
          <VoiceStrip
            voiceState={voiceConversation.voiceState}
            sttPartial={voiceConversation.sttPartial}
            errorMessage={voiceConversation.errorMessage}
            onSpeak={voiceConversation.startListening}
            onSend={voiceConversation.sendNow}
            onStop={voiceConversation.deactivate}
            onInterrupt={voiceConversation.interrupt}
            onRetry={voiceConversation.retry}
          />
        ) : (
          <View style={styles.inputRow}>
            {onSendWithImage ? (
              <Pressable
                onPress={handleAttachPress}
                style={({ pressed }) => [
                  styles.imagePickerButton,
                  activePanel === "attach" && styles.imagePickerButtonActive,
                  pressed && styles.buttonPressed,
                ]}
                hitSlop={8}
                disabled={disabled}
                accessibilityRole="button"
                accessibilityLabel={activePanel === "attach" ? "Close attachment menu" : "Open attachment menu"}
                accessibilityState={{ expanded: activePanel === "attach" }}
              >
                <View style={activePanel !== "none" ? { transform: [{ rotate: "45deg" }] } : undefined}>
                  <SymbolView name={{ ios: "plus", android: "add", web: "add" }} tintColor="#a1a1aa" size={18} weight="medium" />
                </View>
              </Pressable>
            ) : null}

            <TextInput
              style={[
                styles.input,
                speech.isListening && styles.inputDictating,
              ]}
              value={text}
              onChangeText={(newText) => {
                setText(newText);
                if (speech.isListening) speech.stop();
              }}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={speech.isListening ? "Listening..." : `Message ${branding.displayName}...`}
              placeholderTextColor={speech.isListening ? "#ef4444" : "#52525b"}
              multiline
              maxLength={10000}
              editable={!disabled}
              returnKeyType="default"
              blurOnSubmit={false}
              onKeyPress={Platform.OS === "web" ? (e: any) => {
                // Enter sends, Shift+Enter inserts newline
                if (e.nativeEvent.key === "Enter" && !e.nativeEvent.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              } : undefined}
              accessibilityLabel={speech.isListening ? "Listening for speech" : "Message input"}
            />
            {speech.isListening ? (
              <Pressable
                onPress={handleStopDictation}
                style={({ pressed }) => [
                  styles.actionButton,
                  styles.stopDictationButton,
                  pressed && styles.buttonPressed,
                ]}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel="Stop dictation"
              >
                <View style={styles.stopSquare} />
              </Pressable>
            ) : canSend ? (
              <Animated.View style={{ transform: [{ scale: sendButtonScale }] }}>
                <Pressable
                  onPress={handleSend}
                  style={({ pressed }) => [
                    styles.actionButton,
                    styles.sendButton,
                    pressed && styles.buttonPressed,
                  ]}
                  hitSlop={8}
                  accessibilityRole="button"
                  accessibilityLabel="Send message"
                >
                  <SymbolView
                    name={{ ios: "arrow.up", android: "arrow_upward", web: "arrow_upward" }}
                    tintColor="#ffffff"
                    size={18}
                    weight="bold"
                  />
                </Pressable>
              </Animated.View>
            ) : showMic ? (
              <Pressable
                onPress={handleMicPress}
                onLongPress={handleMicLongPress}
                delayLongPress={350}
                style={({ pressed }) => [
                  styles.actionButton,
                  pressed && styles.buttonPressed,
                ]}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel="Start dictation"
                accessibilityHint="Long press for voice mode"
              >
                <SymbolView name={{ ios: "mic.fill", android: "mic", web: "mic" }} tintColor="#8E8E93" size={18} />
              </Pressable>
            ) : null}
          </View>
        )}
      </View>
    </>
  );
}

/** Reusable attach option button */
function AttachOption({
  icon,
  label,
  onPress,
  iconSize = 20,
  iconColor = "#fafafa",
  bgColor,
}: {
  icon: string;
  label: string;
  onPress: () => void;
  iconSize?: number;
  iconColor?: string;
  bgColor?: string;
}) {
  return (
    <Pressable
      style={({ pressed }) => [attachStyles.option, pressed && attachStyles.optionPressed]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <View style={[attachStyles.iconCircle, bgColor ? { backgroundColor: bgColor } : undefined]}>
        <SymbolView name={icon as any} tintColor={iconColor} size={iconSize} />
      </View>
      <Text style={attachStyles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#18181b",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
    paddingHorizontal: 12,
    paddingTop: 8,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "flex-end",
  },
  input: {
    flex: 1,
    backgroundColor: "#27272a",
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: Platform.OS === "ios" ? 10 : 8,
    fontSize: 16,
    color: "#fafafa",
    maxHeight: 120,
    minHeight: 40,
  },
  inputDictating: {
    borderWidth: 1,
    borderColor: "#ef4444",
  },
  actionButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 8,
    marginBottom: 2,
  },
  sendButton: {
    backgroundColor: branding.accentColor,
  },
  stopDictationButton: {
    backgroundColor: "#ef4444",
  },
  stopSquare: {
    width: 12,
    height: 12,
    borderRadius: 2,
    backgroundColor: "#ffffff",
  },
  imagePickerButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "#3f3f46",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 6,
    marginBottom: 2,
  },
  imagePickerButtonActive: {
    backgroundColor: "#52525b",
  },
  buttonPressed: {
    opacity: 0.7,
    transform: [{ scale: 0.92 }],
  },
  pasteBar: {
    backgroundColor: "#1c1c1e",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  pasteBarContent: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  pasteBarText: {
    color: "#a1a1aa",
    fontSize: 14,
  },
  imagePreviewContainer: {
    backgroundColor: "#18181b",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 4,
  },
  imagePreviewWrapper: {
    alignSelf: "flex-start",
    position: "relative",
  },
  imagePreview: {
    width: 72,
    height: 72,
    borderRadius: 10,
    backgroundColor: "#27272a",
  },
  imageRemoveButton: {
    position: "absolute",
    top: -6,
    right: -6,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: "#3f3f46",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "#18181b",
  },
});

const attachStyles = StyleSheet.create({
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    backgroundColor: "#18181b",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 16,
    rowGap: 10,
  },
  option: {
    alignItems: "center",
    gap: 4,
  },
  optionPressed: {
    opacity: 0.6,
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#3f3f46",
    alignItems: "center",
    justifyContent: "center",
  },
  label: {
    color: "#a1a1aa",
    fontSize: 11,
    fontWeight: "500",
  },
});
