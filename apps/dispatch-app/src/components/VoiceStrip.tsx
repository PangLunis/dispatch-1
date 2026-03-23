import React, { useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SymbolView } from "expo-symbols";
import { branding } from "../config/branding";
import type { VoiceState } from "../hooks/useVoiceMode";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface VoiceStripProps {
  voiceState: VoiceState;
  sttPartial: string;
  errorMessage: string | null;
  onSpeak: () => void;
  onSend: () => void;
  onStop: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const NUM_BARS = 5;

export function VoiceStrip({
  voiceState,
  sttPartial,
  errorMessage,
  onSpeak,
  onSend,
  onStop,
}: VoiceStripProps) {
  // Respect reduced motion
  const [reduceMotion, setReduceMotion] = useState(false);
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduceMotion);
    return () => sub.remove();
  }, []);

  // Waveform bar animations
  const barAnims = useRef(
    Array.from({ length: NUM_BARS }, () => new Animated.Value(0.3)),
  ).current;

  useEffect(() => {
    if (reduceMotion || voiceState !== "LISTENING") {
      barAnims.forEach((b) => b.setValue(0.3));
      return;
    }
    const loops: Animated.CompositeAnimation[] = [];
    barAnims.forEach((anim, i) => {
      const duration = 400 + i * 120;
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(anim, {
            toValue: 0.6 + Math.random() * 0.4,
            duration,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(anim, {
            toValue: 0.15 + Math.random() * 0.2,
            duration,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
      );
      loop.start();
      loops.push(loop);
    });
    return () => loops.forEach((l) => l.stop());
  }, [voiceState, barAnims, reduceMotion]);

  // -- Render --

  return (
    <View style={styles.container} accessibilityRole="toolbar" accessibilityLabel="Voice mode">
      {/* Exit button — always visible */}
      <Pressable
        onPress={onStop}
        style={({ pressed }) => [styles.exitButton, pressed && styles.pressed]}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel="Exit voice mode"
        accessibilityHint="Returns to text input"
      >
        <SymbolView name={"xmark" as any} tintColor="#a1a1aa" size={14} weight="bold" />
      </Pressable>

      {/* Center content — varies by state */}
      {voiceState === "IDLE" && !errorMessage && (
        <Pressable
          onPress={onSpeak}
          style={({ pressed }) => [styles.centerArea, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="Tap to speak"
          accessibilityHint="Starts listening for speech"
        >
          <SymbolView name={"mic.fill" as any} tintColor="#71717a" size={18} />
          <Text style={styles.idleText}>Tap to speak</Text>
        </Pressable>
      )}

      {voiceState === "IDLE" && errorMessage && (
        <Pressable
          onPress={onSpeak}
          style={({ pressed }) => [styles.centerArea, pressed && styles.pressed]}
          accessibilityRole="alert"
          accessibilityLabel={errorMessage}
          accessibilityHint="Tap to retry"
        >
          <SymbolView name={"exclamationmark.triangle" as any} tintColor="#fbbf24" size={16} />
          <Text style={styles.errorText} numberOfLines={1}>{errorMessage}</Text>
        </Pressable>
      )}

      {voiceState === "LISTENING" && (
        <View style={styles.listeningRow}>
          <View style={styles.waveformAndText}>
            <View style={styles.waveform} accessibilityElementsHidden>
              {barAnims.map((anim, i) => (
                <Animated.View
                  key={i}
                  style={[
                    styles.waveformBar,
                    { transform: [{ scaleY: anim }] },
                  ]}
                />
              ))}
            </View>
            {sttPartial ? (
              <Text
                style={styles.partialText}
                numberOfLines={1}
                accessibilityLabel={`Heard: ${sttPartial}`}
                accessibilityRole="text"
              >
                {sttPartial}
              </Text>
            ) : (
              <Text style={styles.listeningHint} accessibilityRole="text">
                Listening...
              </Text>
            )}
          </View>
          <Pressable
            onPress={onSend}
            style={({ pressed }) => [styles.sendButton, pressed && styles.pressed]}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Send now"
            accessibilityHint="Sends your speech immediately"
          >
            <SymbolView name={"arrow.up" as any} tintColor="#ffffff" size={16} weight="bold" />
          </Pressable>
        </View>
      )}

      {voiceState === "SENT" && (
        <View style={styles.centerArea} accessibilityRole="text" accessibilityLabel="Message sent">
          <SymbolView name={"checkmark" as any} tintColor="#22c55e" size={18} weight="bold" />
          <Text style={styles.sentText}>Sent!</Text>
        </View>
      )}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#27272a",
    borderRadius: 20,
    minHeight: 40,
    paddingHorizontal: 4,
  },
  exitButton: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: "#3f3f46",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 6,
  },
  centerArea: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 8,
    paddingHorizontal: 8,
  },
  idleText: {
    color: "#71717a",
    fontSize: 15,
    fontWeight: "500",
  },
  errorText: {
    color: "#fbbf24",
    fontSize: 14,
    fontWeight: "500",
    flex: 1,
  },
  listeningRow: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
  },
  waveformAndText: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 8,
    paddingHorizontal: 4,
  },
  waveform: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
    height: 20,
  },
  waveformBar: {
    width: 3,
    height: 20,
    borderRadius: 1.5,
    backgroundColor: "#22c55e",
  },
  partialText: {
    color: "#a1a1aa",
    fontSize: 15,
    flex: 1,
    fontStyle: "italic",
  },
  listeningHint: {
    color: "#52525b",
    fontSize: 15,
    fontStyle: "italic",
  },
  sentText: {
    color: "#22c55e",
    fontSize: 15,
    fontWeight: "600",
  },
  sendButton: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: branding.accentColor,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 6,
    marginRight: 2,
  },
  pressed: {
    opacity: 0.7,
  },
});
