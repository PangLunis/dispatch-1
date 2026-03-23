import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  AppState,
  Image,
  Platform,
  Pressable,
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
import { impactLight } from "../utils/haptics";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useVoiceMode } from "../hooks/useVoiceMode";
import { VoiceStrip } from "./VoiceStrip";
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
}

export function InputBar({ onSend, onSendWithImage, disabled, chatId }: InputBarProps) {
  const [text, setText] = useState("");
  const [selectedAttachment, setSelectedAttachment] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<ActivePanel>("none");
  const speech = useSpeechRecognition();
  const insets = useSafeAreaInsets();

  // Voice mode (long-press mic to activate)
  const voiceMode = useVoiceMode({ onSend });

  const handleMicLongPress = useCallback(() => {
    if (text.trim()) return; // Ignore long-press when text is present — send text first
    voiceMode.activate();
  }, [voiceMode, text]);

  // Track text that was in the field before dictation started
  const [preDictationText, setPreDictationText] = useState("");
  const [clipboardHasImage, setClipboardHasImage] = useState(false);
  const [isFocused, setIsFocused] = useState(false);

  // Check clipboard for images on focus and app foreground (no polling)
  const checkClipboard = useCallback(async () => {
    if (!onSendWithImage || selectedAttachment) return;
    try {
      const hasImage = await Clipboard.hasImageAsync();
      setClipboardHasImage(hasImage);
    } catch {
      setClipboardHasImage(false);
    }
  }, [onSendWithImage, selectedAttachment]);

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
        setSelectedAttachment(uri);
        setClipboardHasImage(false);
        impactLight();
      }
    } catch {
      // Clipboard read failed
    }
  }, []);

  const canSend = (text.trim().length > 0 || selectedAttachment) && !disabled;
  const showMic = !text.trim() && !selectedAttachment && speech.isAvailable && !disabled && !speech.isListening;

  // Sync speech transcript into the text field (skip when voice mode is active —
  // the global STT singleton fires events to both hooks, and useSpeechCapture's
  // activeRef guard handles its side; we suppress the old hook's side here)
  useEffect(() => {
    if (voiceMode.isActive) return;
    if (!speech.isListening && !speech.transcript && !speech.partialTranscript) return;
    const liveText = speech.partialTranscript || speech.transcript;
    if (liveText) {
      const prefix = preDictationText ? preDictationText + " " : "";
      setText(prefix + liveText);
    }
  }, [speech.transcript, speech.partialTranscript, speech.isListening, preDictationText, voiceMode.isActive]);

  const handleSend = useCallback(() => {
    if (!canSend) return;
    impactLight();
    if (speech.isListening) speech.stop();

    if (selectedAttachment && onSendWithImage) {
      onSendWithImage(text.trim(), selectedAttachment);
    } else if (text.trim()) {
      onSend(text.trim());
    }

    setText("");
    setSelectedAttachment(null);
    setPreDictationText("");
    speech.reset();
  }, [canSend, onSend, onSendWithImage, text, selectedAttachment, speech]);

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
      });
      if (!result.canceled && result.assets.length > 0) {
        setSelectedAttachment(result.assets[0].uri);
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
        setSelectedAttachment(result.assets[0].uri);
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
        setSelectedAttachment(result.assets[0].uri);
      }
    } catch (err) {
      console.error("[InputBar] Camera error:", err);
      Alert.alert("Camera Error", "Could not open camera.");
    }
  }, []);

  const handleAttachPress = useCallback(() => {
    impactLight();
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

  const handleRemoveAttachment = useCallback(() => {
    setSelectedAttachment(null);
  }, []);

  return (
    <>
      {clipboardHasImage && !selectedAttachment ? (
        <Pressable
          onPress={handlePasteImage}
          style={styles.pasteBar}
          accessibilityRole="button"
          accessibilityLabel="Paste image from clipboard"
        >
          <View style={styles.pasteBarContent}>
            <SymbolView name="doc.on.clipboard" tintColor="#a1a1aa" size={14} />
            <Text style={styles.pasteBarText}>Paste image from clipboard</Text>
          </View>
        </Pressable>
      ) : null}

      {activePanel === "attach" && onSendWithImage ? (
        <View style={attachStyles.row} accessibilityRole="toolbar" accessibilityLabel="Attachment options">
          <AttachOption icon="camera.fill" label="Camera" onPress={() => handleAttachOption(handleTakePicture)} />
          <AttachOption icon="photo.fill" label="Gallery" onPress={() => handleAttachOption(handlePickFromGallery)} />
          <AttachOption icon="folder.fill" label="Files" onPress={() => handleAttachOption(handlePickFromFiles)} />
          <AttachOption icon="bubble.left.and.bubble.right.fill" label="Sessions" iconSize={18} onPress={handleOpenSessionPicker} />
          <AttachOption icon="wrench.and.screwdriver.fill" label="Skills" iconColor="#38bdf8" onPress={handleOpenSkillPicker} />
          <AttachOption icon="checkmark.seal.fill" label="Review" iconColor="#a78bfa" onPress={handleReview} />
          <AttachOption icon="hammer.fill" label="Build" iconColor="#f59e0b" onPress={handlePlanBuildTest} />
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

      {selectedAttachment ? (
        <View style={styles.imagePreviewContainer}>
          <View style={styles.imagePreviewWrapper}>
            <Image
              source={{ uri: selectedAttachment }}
              style={styles.imagePreview}
              accessibilityLabel="Selected attachment preview"
            />
            <Pressable
              onPress={handleRemoveAttachment}
              style={styles.imageRemoveButton}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityLabel="Remove attachment"
            >
              <SymbolView name="xmark" tintColor="#fafafa" size={10} weight="bold" />
            </Pressable>
          </View>
        </View>
      ) : null}

      <View style={[styles.container, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        {voiceMode.isActive ? (
          <VoiceStrip
            voiceState={voiceMode.voiceState}
            sttPartial={voiceMode.sttPartial}
            errorMessage={voiceMode.errorMessage}
            onSpeak={voiceMode.startListening}
            onSend={voiceMode.sendNow}
            onStop={voiceMode.deactivate}
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
                  <SymbolView name="plus" tintColor="#a1a1aa" size={18} weight="medium" />
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
              onSubmitEditing={Platform.OS === "web" ? handleSend : undefined}
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
                  name="arrow.up"
                  tintColor="#ffffff"
                  size={18}
                  weight="bold"
                />
              </Pressable>
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
                <SymbolView name="mic.fill" tintColor="#8E8E93" size={18} />
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
