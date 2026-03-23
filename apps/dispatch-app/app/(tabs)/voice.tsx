import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  Animated,
  Easing,
  LayoutAnimation,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { SymbolView } from "expo-symbols";
import { branding } from "@/src/config/branding";
import {
  useVoiceAgent,
  STATE_LABELS,
  STATE_COLORS,
} from "@/src/hooks/useVoiceAgent";

// ---------------------------------------------------------------------------
// SF Symbol wrapper — text fallback on non-iOS
// ---------------------------------------------------------------------------

function Icon({
  name,
  tintColor,
  size,
  fallback,
}: {
  name: string;
  tintColor: string;
  size: number;
  fallback?: string;
}) {
  if (Platform.OS === "ios") {
    return <SymbolView name={name as any} tintColor={tintColor} size={size} />;
  }
  return fallback ? (
    <Text style={{ color: tintColor, fontSize: size }}>{fallback}</Text>
  ) : null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function VoiceScreen() {
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollView>(null);
  const voice = useVoiceAgent();
  const isVoiceActive = voice.voiceState === "LISTENING" || voice.voiceState === "WAITING";

  // Respect reduced motion preference
  const [reduceMotion, setReduceMotion] = useState(false);
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduceMotion);
    return () => sub.remove();
  }, []);

  // Animate layout when control buttons change (respects reduced motion)
  // Also announce state transitions to VoiceOver
  const prevVoiceState = useRef(voice.voiceState);
  useEffect(() => {
    if (prevVoiceState.current !== voice.voiceState) {
      if (!reduceMotion) {
        LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
      }
      // Announce meaningful transitions to screen readers
      const announcements: Partial<Record<string, string>> = {
        IDLE: "Stopped",
        LISTENING: "Listening for speech",
        WAITING: "Processing your message",
        ERROR: voice.errorMessage || "An error occurred",
      };
      const msg = announcements[voice.voiceState];
      if (msg) {
        AccessibilityInfo.announceForAccessibility(msg);
      }
      prevVoiceState.current = voice.voiceState;
    }
  }, [voice.voiceState, reduceMotion, voice.errorMessage]);

  // Auto-scroll on content change
  const handleContentSizeChange = useCallback(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, []);

  // Pulse animation for state dot and button ring (respects reduced motion)
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const ringAnim = useRef(new Animated.Value(0)).current;

  // Waveform bars animation for LISTENING state
  const NUM_BARS = 5;
  const barAnims = useRef(
    Array.from({ length: NUM_BARS }, () => new Animated.Value(0.3)),
  ).current;

  useEffect(() => {
    if (reduceMotion) {
      pulseAnim.setValue(1);
      ringAnim.setValue(0);
      barAnims.forEach((b) => b.setValue(0.3));
      return;
    }
    if (voice.voiceState === "LISTENING" || voice.voiceState === "WAITING") {
      const duration = voice.voiceState === "LISTENING" ? 600 : 1200;
      const toValue = voice.voiceState === "LISTENING" ? 1.4 : 1.2;
      const dotLoop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue,
            duration,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
      );
      const ringLoop = Animated.loop(
        Animated.sequence([
          Animated.timing(ringAnim, {
            toValue: 1,
            duration: voice.voiceState === "LISTENING" ? 800 : 1500,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(ringAnim, {
            toValue: 0,
            duration: voice.voiceState === "LISTENING" ? 800 : 1500,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
      );
      dotLoop.start();
      ringLoop.start();

      // Waveform bars — only during LISTENING
      const barLoops: Animated.CompositeAnimation[] = [];
      if (voice.voiceState === "LISTENING") {
        barAnims.forEach((anim, i) => {
          const barDuration = 400 + i * 120; // Stagger durations for organic feel
          const loop = Animated.loop(
            Animated.sequence([
              Animated.timing(anim, {
                toValue: 0.6 + Math.random() * 0.4,
                duration: barDuration,
                easing: Easing.inOut(Easing.ease),
                useNativeDriver: true,
              }),
              Animated.timing(anim, {
                toValue: 0.15 + Math.random() * 0.2,
                duration: barDuration,
                easing: Easing.inOut(Easing.ease),
                useNativeDriver: true,
              }),
            ]),
          );
          loop.start();
          barLoops.push(loop);
        });
      } else {
        barAnims.forEach((b) => b.setValue(0.3));
      }

      return () => {
        dotLoop.stop();
        ringLoop.stop();
        barLoops.forEach((l) => l.stop());
      };
    } else {
      pulseAnim.setValue(1);
      ringAnim.setValue(0);
      barAnims.forEach((b) => b.setValue(0.3));
    }
  }, [voice.voiceState, pulseAnim, ringAnim, barAnims, reduceMotion]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <View style={styles.container}>
      {/* Chat picker bar */}
      <View style={[styles.pickerBar, { paddingTop: Math.max(insets.top, 8) }]}>
        <Pressable
          style={({ pressed }) => [
            styles.pickerButton,
            isVoiceActive && styles.pickerDisabled,
            pressed && !isVoiceActive && styles.pressed,
          ]}
          onPress={isVoiceActive ? undefined : voice.showChatPicker}
          disabled={isVoiceActive}
          accessibilityRole="button"
          accessibilityLabel={`Select chat. Currently: ${voice.selectedLabel}`}
          accessibilityHint={isVoiceActive ? undefined : "Opens chat selection menu"}
          accessibilityState={{ disabled: isVoiceActive }}
        >
          <Icon
            name="bubble.left.and.text.bubble.right"
            tintColor="#71717a"
            size={16}
            fallback="chat"
          />
          <Text style={styles.pickerValue} numberOfLines={1}>
            {voice.selectedLabel}
          </Text>
          <Icon name="chevron.down" tintColor="#52525b" size={12} fallback="v" />
        </Pressable>
      </View>

      {/* Transcript */}
      <ScrollView
        ref={scrollRef}
        style={styles.transcript}
        contentContainerStyle={[
          styles.transcriptContent,
          voice.entries.length === 0 && styles.transcriptContentEmpty,
        ]}
        keyboardShouldPersistTaps="handled"
        onContentSizeChange={handleContentSizeChange}
      >
        {voice.entries.length === 0 && voice.voiceState === "IDLE" && (
          <View
            style={styles.emptyState}
            accessibilityRole="text"
            accessibilityLabel="Voice Brainstorm. Speak freely — your words become messages, and the agent responds. Tap Start Voice to begin."
          >
            <Icon name="waveform" tintColor="#52525b" size={72} />
            <Text style={styles.emptyTitle}>Voice Brainstorm</Text>
            <Text style={styles.emptySubtitle}>
              Speak freely — your words become messages, and the agent responds.
            </Text>
          </View>
        )}

        {voice.entries.map((entry) => (
          <View
            key={entry.key}
            style={[
              styles.bubble,
              entry.role === "user" ? styles.userBubble : styles.assistantBubble,
            ]}
            accessibilityRole="text"
            accessibilityLabel={`${entry.role === "user" ? "You" : "Assistant"}: ${entry.text}`}
          >
            <Text
              style={[
                styles.bubbleText,
                entry.role === "user"
                  ? styles.userBubbleText
                  : styles.assistantBubbleText,
              ]}
            >
              {entry.text}
            </Text>
          </View>
        ))}

        {/* Live partial transcript (hidden from VoiceOver — final text announced when committed) */}
        {voice.voiceState === "LISTENING" &&
        (voice.sttPartial || voice.sttTranscript) ? (
          <View
            style={[styles.bubble, styles.userBubble, styles.partialBubble]}
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
          >
            <Text style={[styles.bubbleText, styles.userBubbleText]}>
              {voice.sttPartial || voice.sttTranscript}
            </Text>
          </View>
        ) : null}

        {/* Agent text streaming (hidden from VoiceOver — final text announced when committed) */}
        {voice.currentAgentText ? (
          <View
            style={[
              styles.bubble,
              styles.assistantBubble,
              styles.partialBubble,
            ]}
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
          >
            <Text style={[styles.bubbleText, styles.assistantBubbleText]}>
              {voice.currentAgentText}
            </Text>
          </View>
        ) : null}

        {/* Error */}
        {voice.voiceState === "ERROR" && voice.errorMessage ? (
          <View style={styles.errorContainer} accessibilityRole="alert">
            <Text style={styles.errorText}>{voice.errorMessage}</Text>
          </View>
        ) : null}
      </ScrollView>

      {/* State indicator — announceForAccessibility handles VoiceOver updates */}
      <View
        style={styles.stateBar}
        accessibilityRole="text"
        accessibilityLabel={`Voice state: ${STATE_LABELS[voice.voiceState]}`}
      >
        {voice.voiceState === "LISTENING" && !reduceMotion ? (
          <View style={styles.waveformContainer} accessibilityElementsHidden>
            {barAnims.map((anim, i) => (
              <Animated.View
                key={i}
                style={[
                  styles.waveformBar,
                  {
                    backgroundColor: STATE_COLORS.LISTENING,
                    transform: [{ scaleY: anim }],
                  },
                ]}
              />
            ))}
          </View>
        ) : (
          <Animated.View
            style={[
              styles.stateDot,
              { backgroundColor: STATE_COLORS[voice.voiceState] },
              (voice.voiceState === "LISTENING" ||
                voice.voiceState === "WAITING") && {
                transform: [{ scale: pulseAnim }],
              },
            ]}
          />
        )}
        <Text
          style={[
            styles.stateText,
            { color: STATE_COLORS[voice.voiceState] },
          ]}
        >
          {STATE_LABELS[voice.voiceState]}
        </Text>
      </View>

      {/* Controls */}
      <View
        style={[styles.controls, { paddingBottom: Math.max(insets.bottom, 16) }]}
        accessibilityState={{ busy: voice.voiceState === "WAITING" }}
      >
        {voice.voiceState === "IDLE" && (
          <Pressable
            style={({ pressed }) => [styles.startButton, pressed && styles.pressed]}
            onPress={voice.startListening}
            accessibilityRole="button"
            accessibilityLabel="Start voice recording"
            accessibilityHint="Begins listening for speech"
          >
            <Icon name="mic.fill" tintColor="#ffffff" size={20} />
            <Text style={styles.startButtonText}>Start Voice</Text>
          </Pressable>
        )}

        {voice.voiceState === "LISTENING" && (
          <View style={styles.listeningControls}>
            <Pressable
              style={({ pressed }) => [styles.stopButton, pressed && styles.pressed]}
              onPress={voice.stopAll}
              accessibilityRole="button"
              accessibilityLabel="Stop recording"
              accessibilityHint="Stops listening and discards current speech"
            >
              <Icon name="stop.fill" tintColor="#fafafa" size={16} />
              <Text style={styles.stopButtonText}>Stop</Text>
            </Pressable>
            <View style={styles.sendButtonWrapper}>
              <Animated.View
                style={[
                  styles.listeningRing,
                  {
                    opacity: ringAnim.interpolate({
                      inputRange: [0, 1],
                      outputRange: [0.3, 0.8],
                    }),
                    transform: [{
                      scale: ringAnim.interpolate({
                        inputRange: [0, 1],
                        outputRange: [1, 1.06],
                      }),
                    }],
                  },
                ]}
              />
              <Pressable
                style={({ pressed }) => [styles.sendButton, pressed && styles.pressed]}
                onPress={voice.sendNow}
                accessibilityRole="button"
                accessibilityLabel="Send now"
                accessibilityHint="Sends your speech to the agent immediately"
              >
                <Icon name="arrow.up" tintColor="#ffffff" size={16} />
                <Text style={styles.startButtonText}>Send</Text>
              </Pressable>
            </View>
          </View>
        )}

        {voice.voiceState === "WAITING" && (
          <Pressable
            style={({ pressed }) => [styles.stopButton, pressed && styles.pressed]}
            onPress={voice.stopAll}
            accessibilityRole="button"
            accessibilityLabel="Cancel request"
            accessibilityHint="Cancels the agent request and returns to idle"
          >
            <Icon name="xmark" tintColor="#fafafa" size={16} />
            <Text style={styles.stopButtonText}>Cancel</Text>
          </Pressable>
        )}

        {voice.voiceState === "ERROR" && (
          <View style={styles.errorControls}>
            <Pressable
              style={({ pressed }) => [styles.retryButton, pressed && styles.pressed]}
              onPress={voice.retryFromError}
              accessibilityRole="button"
              accessibilityLabel="Retry recording"
              accessibilityHint="Restarts speech recognition"
            >
              <Icon name="arrow.counterclockwise" tintColor="#ffffff" size={16} />
              <Text style={styles.startButtonText}>Retry</Text>
            </Pressable>
            <Pressable
              style={({ pressed }) => [styles.stopButton, pressed && styles.pressed]}
              onPress={voice.stopAll}
              accessibilityRole="button"
              accessibilityLabel="Stop and reset"
              accessibilityHint="Stops everything and returns to idle"
            >
              <Icon name="stop.fill" tintColor="#fafafa" size={16} />
              <Text style={styles.stopButtonText}>Stop</Text>
            </Pressable>
          </View>
        )}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  // -- Chat picker --
  pickerBar: {
    paddingHorizontal: 16,
    paddingBottom: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  pickerButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "#18181b",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    minHeight: 44, // iOS minimum touch target
  },
  pickerDisabled: {
    opacity: 0.4,
  },
  pickerValue: {
    color: "#fafafa",
    fontSize: 15,
    fontWeight: "600",
    flex: 1,
  },
  // -- Transcript --
  transcript: {
    flex: 1,
  },
  transcriptContent: {
    padding: 16,
    paddingBottom: 8,
  },
  transcriptContentEmpty: {
    flexGrow: 1,
    justifyContent: "center",
  },
  emptyState: {
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    paddingBottom: 60,
  },
  emptyTitle: {
    fontSize: 22,
    fontWeight: "700",
    color: "#fafafa",
  },
  emptySubtitle: {
    fontSize: 15,
    color: "#71717a",
    textAlign: "center",
    paddingHorizontal: 48,
    lineHeight: 22,
  },
  bubble: {
    maxWidth: "80%",
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginBottom: 8,
  },
  userBubble: {
    alignSelf: "flex-end",
    backgroundColor: branding.accentColor,
  },
  assistantBubble: {
    alignSelf: "flex-start",
    backgroundColor: "#27272a",
  },
  partialBubble: {
    opacity: 0.6,
    borderWidth: 1,
    borderColor: "#3f3f46",
    borderStyle: "dashed",
  },
  bubbleText: {
    fontSize: 16,
    lineHeight: 22,
  },
  userBubbleText: {
    color: "#ffffff",
  },
  assistantBubbleText: {
    color: "#fafafa",
  },
  errorContainer: {
    alignSelf: "center",
    backgroundColor: "#7f1d1d",
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginBottom: 8,
  },
  errorText: {
    color: "#fca5a5",
    fontSize: 14,
    textAlign: "center",
  },
  // -- State bar --
  stateBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
  },
  stateDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  waveformContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    marginRight: 10,
    height: 18,
  },
  waveformBar: {
    width: 3,
    height: 18,
    borderRadius: 1.5,
  },
  stateText: {
    fontSize: 14,
    fontWeight: "600",
  },
  // -- Controls --
  controls: {
    paddingHorizontal: 24,
    paddingTop: 8,
  },
  startButton: {
    backgroundColor: branding.accentColor,
    borderRadius: 28,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  startButtonText: {
    color: "#ffffff",
    fontSize: 17,
    fontWeight: "700",
  },
  listeningControls: {
    flexDirection: "row",
    gap: 12,
  },
  sendButtonWrapper: {
    position: "relative",
    flex: 1,
  },
  sendButton: {
    backgroundColor: branding.accentColor,
    borderRadius: 28,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  listeningRing: {
    position: "absolute",
    top: -3,
    left: -3,
    right: -3,
    bottom: -3,
    borderRadius: 31,
    borderWidth: 2,
    borderColor: branding.accentColor,
  },
  stopButton: {
    backgroundColor: "#3f3f46",
    borderRadius: 28,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    flex: 1,
  },
  stopButtonText: {
    color: "#fafafa",
    fontSize: 17,
    fontWeight: "700",
  },
  errorControls: {
    flexDirection: "row",
    gap: 12,
  },
  retryButton: {
    backgroundColor: branding.accentColor,
    borderRadius: 28,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    flex: 1,
  },
  pressed: {
    opacity: 0.7,
    transform: [{ scale: 0.97 }],
  },
});
