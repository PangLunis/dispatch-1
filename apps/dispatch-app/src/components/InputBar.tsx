import React, { useCallback, useEffect, useRef, useState } from "react";
import {
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
import * as Clipboard from "expo-clipboard";
import * as FileSystem from "expo-file-system/legacy";
import { SymbolView } from "expo-symbols";
import { branding } from "../config/branding";
import { impactLight } from "../utils/haptics";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";

interface InputBarProps {
  onSend: (text: string) => void;
  onSendWithImage?: (text: string, imageUri: string) => void;
  disabled?: boolean;
}

export function InputBar({ onSend, onSendWithImage, disabled }: InputBarProps) {
  const [text, setText] = useState("");
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const speech = useSpeechRecognition();
  const insets = useSafeAreaInsets();

  // Track text that was in the field before dictation started
  const [preDictationText, setPreDictationText] = useState("");
  const [clipboardHasImage, setClipboardHasImage] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const clipboardCheckRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Check clipboard for images when input is focused
  useEffect(() => {
    if (!isFocused || !onSendWithImage || selectedImage) {
      setClipboardHasImage(false);
      if (clipboardCheckRef.current) {
        clearInterval(clipboardCheckRef.current);
        clipboardCheckRef.current = null;
      }
      return;
    }

    const checkClipboard = async () => {
      try {
        const hasImage = await Clipboard.hasImageAsync();
        setClipboardHasImage(hasImage);
      } catch {
        setClipboardHasImage(false);
      }
    };

    // Check immediately and then every 2 seconds while focused
    checkClipboard();
    clipboardCheckRef.current = setInterval(checkClipboard, 2000);

    return () => {
      if (clipboardCheckRef.current) {
        clearInterval(clipboardCheckRef.current);
        clipboardCheckRef.current = null;
      }
    };
  }, [isFocused, onSendWithImage, selectedImage]);

  const handlePasteImage = useCallback(async () => {
    try {
      const clipImage = await Clipboard.getImageAsync({ format: "png" });
      if (clipImage && clipImage.data) {
        // clipImage.data is a base64 string — write to temp file
        const filename = `clipboard_${Date.now()}.png`;
        const uri = FileSystem.cacheDirectory + filename;
        await FileSystem.writeAsStringAsync(uri, clipImage.data, {
          encoding: FileSystem.EncodingType.Base64,
        });
        setSelectedImage(uri);
        setClipboardHasImage(false);
        impactLight();
      }
    } catch {
      // Clipboard read failed
    }
  }, []);

  const canSend = (text.trim().length > 0 || selectedImage) && !disabled;
  // Show mic button when: no text typed, no image selected, speech is available, not disabled, and not currently dictating
  const showMic = !text.trim() && !selectedImage && speech.isAvailable && !disabled && !speech.isListening;

  // Sync speech transcript into the text field (inline dictation like iMessage)
  useEffect(() => {
    if (!speech.isListening && !speech.transcript && !speech.partialTranscript) return;

    const liveText = speech.partialTranscript || speech.transcript;
    if (liveText) {
      const prefix = preDictationText ? preDictationText + " " : "";
      setText(prefix + liveText);
    }
  }, [speech.transcript, speech.partialTranscript, speech.isListening, preDictationText]);

  const handleSend = useCallback(() => {
    if (!canSend) return;
    impactLight();

    // Stop dictation if active
    if (speech.isListening) {
      speech.stop();
    }

    if (selectedImage && onSendWithImage) {
      onSendWithImage(text.trim(), selectedImage);
    } else if (text.trim()) {
      onSend(text.trim());
    }

    setText("");
    setSelectedImage(null);
    setPreDictationText("");
    speech.reset();
  }, [canSend, onSend, onSendWithImage, text, selectedImage, speech]);

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

  const handlePickImage = useCallback(async () => {
    impactLight();
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.8,
      allowsEditing: false,
    });

    if (!result.canceled && result.assets.length > 0) {
      setSelectedImage(result.assets[0].uri);
    }
  }, []);

  const handleRemoveImage = useCallback(() => {
    setSelectedImage(null);
  }, []);

  return (
    <>
      {clipboardHasImage && !selectedImage ? (
        <Pressable
          onPress={handlePasteImage}
          style={styles.pasteBar}
        >
          <Text style={styles.pasteBarText}>📋 Paste image from clipboard</Text>
        </Pressable>
      ) : null}

      {selectedImage ? (
        <View style={styles.imagePreviewContainer}>
          <View style={styles.imagePreviewWrapper}>
            <Image
              source={{ uri: selectedImage }}
              style={styles.imagePreview}
            />
            <Pressable
              onPress={handleRemoveImage}
              style={styles.imageRemoveButton}
              hitSlop={8}
            >
              <View style={styles.imageRemoveX}>
                <View style={[styles.xLine, styles.xLine1]} />
                <View style={[styles.xLine, styles.xLine2]} />
              </View>
            </Pressable>
          </View>
        </View>
      ) : null}

      <View style={[styles.container, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <View style={styles.inputRow}>
          {/* Image picker button — shown when onSendWithImage is provided */}
          {onSendWithImage ? (
            <Pressable
              onPress={handlePickImage}
              style={({ pressed }) => [
                styles.imagePickerButton,
                pressed && styles.buttonPressed,
              ]}
              hitSlop={8}
              disabled={disabled}
            >
              <ImageIcon />
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
              // If user manually edits during dictation, stop dictation
              if (speech.isListening) {
                speech.stop();
              }
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
          />
          {speech.isListening ? (
            <Pressable
              onPress={handleStopDictation}
              style={({ pressed }) => [
                styles.stopDictationButton,
                pressed && styles.buttonPressed,
              ]}
              hitSlop={8}
            >
              <View style={styles.stopSquare} />
            </Pressable>
          ) : canSend ? (
            <Pressable
              onPress={handleSend}
              style={({ pressed }) => [
                styles.sendButton,
                pressed && styles.buttonPressed,
              ]}
              hitSlop={8}
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
              style={({ pressed }) => [
                styles.micButton,
                pressed && styles.buttonPressed,
              ]}
              hitSlop={8}
            >
              <MicIcon />
            </Pressable>
          ) : null}
        </View>
      </View>
    </>
  );
}

/** Microphone icon drawn with RN Views */
function MicIcon() {
  return (
    <View style={micStyles.container}>
      {/* Mic body */}
      <View style={micStyles.body} />
      {/* Mic arc (simplified as a border-bottom-radius view) */}
      <View style={micStyles.arc} />
      {/* Stem */}
      <View style={micStyles.stem} />
    </View>
  );
}

/** Plus icon matching iMessage style */
function ImageIcon() {
  return (
    <View style={imageIconStyles.container}>
      {/* Horizontal bar */}
      <View style={imageIconStyles.hBar} />
      {/* Vertical bar */}
      <View style={imageIconStyles.vBar} />
    </View>
  );
}

const micStyles = StyleSheet.create({
  container: {
    width: 16,
    height: 18,
    alignItems: "center",
  },
  body: {
    width: 8,
    height: 10,
    borderRadius: 4,
    backgroundColor: "#8E8E93",
  },
  arc: {
    width: 12,
    height: 6,
    borderWidth: 2,
    borderColor: "#8E8E93",
    borderTopWidth: 0,
    borderBottomLeftRadius: 6,
    borderBottomRightRadius: 6,
    marginTop: -2,
  },
  stem: {
    width: 2,
    height: 4,
    backgroundColor: "#8E8E93",
    marginTop: -1,
  },
});

const imageIconStyles = StyleSheet.create({
  container: {
    width: 18,
    height: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  hBar: {
    position: "absolute",
    width: 14,
    height: 2,
    borderRadius: 1,
    backgroundColor: "#a1a1aa",
  },
  vBar: {
    position: "absolute",
    width: 2,
    height: 14,
    borderRadius: 1,
    backgroundColor: "#a1a1aa",
  },
});

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#18181b",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
    paddingHorizontal: 12,
    paddingTop: 8,
    // paddingBottom is set dynamically via useSafeAreaInsets
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
  sendButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: branding.accentColor,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 8,
    marginBottom: 2,
  },
  micButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 8,
    marginBottom: 2,
  },
  stopDictationButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "#ef4444",
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 8,
    marginBottom: 2,
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
  imageRemoveX: {
    width: 10,
    height: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  xLine: {
    position: "absolute",
    width: 10,
    height: 1.5,
    backgroundColor: "#fafafa",
  },
  xLine1: {
    transform: [{ rotate: "45deg" }],
  },
  xLine2: {
    transform: [{ rotate: "-45deg" }],
  },
});
