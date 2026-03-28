import { useCallback, useEffect, useRef, useState } from "react";
import { AccessibilityInfo, AppState, Keyboard, LayoutAnimation } from "react-native";
import { useSpeechCapture } from "./useSpeechCapture";
import { useAutoTTS } from "./useAutoTTS";
import { impactLight, impactMedium, notificationError } from "../utils/haptics";
import { branding } from "../config/branding";
import type { DisplayMessage } from "./useMessages";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ConversationVoiceState =
  | "IDLE"
  | "LISTENING"
  | "SPEAKING"
  | "ERROR";

export interface VoiceConversationReturn {
  isActive: boolean;
  voiceState: ConversationVoiceState;
  sttPartial: string;
  errorMessage: string | null;

  activate: () => Promise<void>;
  deactivate: () => void;
  startListening: () => Promise<void>;
  sendNow: () => void;
  retry: () => void;
  interrupt: () => void;
}

export interface VoiceConversationOptions {
  chatId: string;
  /** Send message through normal chat flow (same as typed messages). */
  onSend: (text: string) => void;
  /** Current messages array from useMessages — used to detect new assistant responses. */
  messages: DisplayMessage[];
  /** Called when voice mode activates so the parent can clear the text input. */
  onClearText?: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MIN_TRANSCRIPT_LENGTH = 3;
const MAX_CONSECUTIVE_ERRORS = 3;
const LISTENING_TIMEOUT_MS = 120_000; // 2 minutes — generous for long pauses

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useVoiceConversation(
  options: VoiceConversationOptions,
): VoiceConversationReturn {
  const { chatId, onSend, messages, onClearText } = options;

  // iOS audio session config for STT during TTS playback — enables hardware echo
  // cancellation (AEC) via .voiceChat mode so the mic doesn't pick up TTS audio
  // from the speaker. Uses .playAndRecord with .mixWithOthers so AVPlayer and
  // AVAudioEngine coexist. Note: .voiceChat mode may route audio to earpiece
  // instead of the loud speaker — this is expected for voice conversations (like
  // a phone call) and is what enables Apple's built-in AEC.
  const voiceInterruptIosCategory = useRef({
    category: "playAndRecord",
    categoryOptions: ["defaultToSpeaker", "allowBluetooth", "mixWithOthers"],
    mode: "voiceChat", // enables AEC — prevents TTS audio from triggering STT
  }).current;

  // -- Sub-hooks --
  const {
    isListening: sttIsListening,
    transcript: sttTranscript,
    partial: sttPartial,
    error: sttError,
    start: sttStart,
    stop: sttStop,
    reset: sttReset,
  } = useSpeechCapture({
    contextualStrings: [branding.displayName],
    // Pass iosCategory so STT doesn't override the audio session during TTS playback
    iosCategory: voiceInterruptIosCategory,
  });

  // Auto-TTS with callbacks wired to state machine
  const tts = useAutoTTS({
    onComplete: () => {
      // TTS finished → auto-start listening for next turn
      if (isActiveRef.current && voiceStateRef.current === "SPEAKING") {
        transitionTo("LISTENING");
        startSTT();
      }
    },
    onError: () => {
      // TTS failed → skip to listening (graceful degradation)
      if (isActiveRef.current && voiceStateRef.current === "SPEAKING") {
        transitionTo("LISTENING");
        startSTT();
      }
    },
  });

  // -- State --
  const [isActive, setIsActive] = useState(false);
  const [voiceState, setVoiceState] = useState<ConversationVoiceState>("IDLE");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // -- Refs --
  const isActiveRef = useRef(false);
  const voiceStateRef = useRef<ConversationVoiceState>("IDLE");
  const isActivatingRef = useRef(false);
  const consecutiveErrorRef = useRef(0);
  const activeSessionRef = useRef(0); // Concurrency guard
  const listeningTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voiceInterruptTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasSentRef = useRef(false);
  // Guard to suppress STT auto-restart during the SPEAKING transition.
  // Without this, sttStop() triggers the "restart STT on end during SPEAKING"
  // effect IMMEDIATELY, defeating the 750ms delay designed to avoid picking up TTS audio.
  const suppressSttRestartRef = useRef(false);

  // Track last seen assistant message to detect new responses
  const lastSeenAssistantIdRef = useRef<string | null>(null);

  // Keep STT values in refs for callbacks
  const sttPartialRef = useRef(sttPartial);
  sttPartialRef.current = sttPartial;
  const sttTranscriptRef = useRef(sttTranscript);
  sttTranscriptRef.current = sttTranscript;
  const onSendRef = useRef(onSend);
  onSendRef.current = onSend;
  const onClearTextRef = useRef(onClearText);
  onClearTextRef.current = onClearText;

  // Sync refs
  useEffect(() => { isActiveRef.current = isActive; }, [isActive]);
  useEffect(() => { voiceStateRef.current = voiceState; }, [voiceState]);

  // -- Helpers --

  const clearTimeouts = useCallback(() => {
    if (listeningTimeoutRef.current) {
      clearTimeout(listeningTimeoutRef.current);
      listeningTimeoutRef.current = null;
    }
    if (voiceInterruptTimerRef.current) {
      clearTimeout(voiceInterruptTimerRef.current);
      voiceInterruptTimerRef.current = null;
    }
  }, []);

  const transitionTo = useCallback(
    (state: ConversationVoiceState, error?: string) => {
      clearTimeouts();
      setVoiceState(state);
      voiceStateRef.current = state;
      if (error) {
        setErrorMessage(error);
      } else if (state !== "ERROR") {
        setErrorMessage(null);
      }
    },
    [clearTimeouts],
  );

  /** Start STT and set listening timeout. */
  const startSTT = useCallback(async () => {
    hasSentRef.current = false;
    sttReset();
    try {
      await sttStart();
      // Set listening timeout
      listeningTimeoutRef.current = setTimeout(() => {
        if (voiceStateRef.current === "LISTENING" && isActiveRef.current) {
          transitionTo("ERROR", "Didn't hear anything — tap to try again");
          notificationError();
        }
      }, LISTENING_TIMEOUT_MS);
    } catch (err) {
      console.warn("[VoiceConversation] STT start failed:", err);
      transitionTo("ERROR", "Microphone unavailable — tap to try again");
      notificationError();
    }
  }, [sttStart, sttReset, transitionTo]);

  // -- Cleanup helper --

  const resetAll = useCallback(() => {
    clearTimeouts();
    sttStop();
    tts.interrupt();
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setIsActive(false);
    setVoiceState("IDLE");
    setErrorMessage(null);
    consecutiveErrorRef.current = 0;
    isActivatingRef.current = false;
    hasSentRef.current = false;
    suppressSttRestartRef.current = false;
  }, [clearTimeouts, sttStop, tts]);

  // -- Actions --

  const activate = useCallback(async () => {
    if (isActivatingRef.current || isActiveRef.current) return;
    isActivatingRef.current = true;
    activeSessionRef.current++;
    const sessionId = activeSessionRef.current;

    impactMedium();
    Keyboard.dismiss();

    // Snapshot the last assistant message so we don't auto-play old ones
    const lastAssistant = findLastAssistantMessage(messages);
    lastSeenAssistantIdRef.current = lastAssistant?.id ?? null;

    // Clear text box
    onClearTextRef.current?.();

    // Wait for keyboard to dismiss
    await new Promise<void>((resolve) => {
      const sub = Keyboard.addListener("keyboardDidHide", () => {
        sub.remove();
        resolve();
      });
      setTimeout(() => { sub.remove(); resolve(); }, 250);
    });

    // Check session is still valid (rapid exit/re-enter guard)
    if (activeSessionRef.current !== sessionId) return;

    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setIsActive(true);
    setErrorMessage(null);
    consecutiveErrorRef.current = 0;
    AccessibilityInfo.announceForAccessibility("Voice mode activated, listening");

    transitionTo("LISTENING");
    await startSTT();
    isActivatingRef.current = false;
  }, [transitionTo, startSTT, messages]);

  const deactivate = useCallback(() => {
    activeSessionRef.current++;
    resetAll();
    impactLight();
    AccessibilityInfo.announceForAccessibility("Voice mode off");
  }, [resetAll]);

  const startListening = useCallback(async () => {
    transitionTo("LISTENING");
    impactLight();
    await startSTT();
  }, [transitionTo, startSTT]);

  /** Shared: validate transcript and send via normal chat flow, then restart listening. */
  const submitTranscript = useCallback((rawText: string) => {
    if (hasSentRef.current) return;
    clearTimeouts();

    const trimmed = rawText.trim();
    if (trimmed.length >= MIN_TRANSCRIPT_LENGTH) {
      hasSentRef.current = true;
      impactMedium();
      AccessibilityInfo.announceForAccessibility("Message sent");

      // Send through normal chat flow — same as typed messages
      onSendRef.current(trimmed);

      // Immediately restart listening so user can keep talking
      consecutiveErrorRef.current = 0;
      transitionTo("LISTENING");
      startSTT();
    } else {
      // Too short or empty — just keep listening, don't show error
      consecutiveErrorRef.current++;
      if (consecutiveErrorRef.current >= MAX_CONSECUTIVE_ERRORS) {
        transitionTo("ERROR", "Having trouble hearing you — tap to try again");
        consecutiveErrorRef.current = 0;
      } else {
        transitionTo("LISTENING");
        startSTT();
      }
    }
  }, [clearTimeouts, transitionTo, deactivate, startSTT]);

  const sendNow = useCallback(() => {
    if (voiceStateRef.current !== "LISTENING") return;
    const text = sttPartialRef.current || sttTranscriptRef.current;
    sttStop();
    submitTranscript(text || "");
  }, [sttStop, submitTranscript]);

  const retry = useCallback(() => {
    transitionTo("LISTENING");
    startSTT();
  }, [transitionTo, startSTT]);

  const interrupt = useCallback(() => {
    if (voiceStateRef.current === "SPEAKING") {
      tts.interrupt();
      transitionTo("LISTENING");
      startSTT();
    }
  }, [tts, transitionTo, startSTT]);

  // -- Effects: Bridge STT events → state machine --

  // STT error — for "no speech detected" type errors, just silently restart listening
  useEffect(() => {
    if (!sttError || !isActiveRef.current) return;
    if (voiceStateRef.current !== "LISTENING") return;

    // Strip sequence suffix added by useSpeechCapture (e.g., "no speech detected|3")
    const errorMsg = sttError.replace(/\|\d+$/, "");

    const isNoSpeech = /no speech|no match|not available/i.test(errorMsg);
    if (isNoSpeech) {
      // Silently restart — user might just be pausing between thoughts
      console.log("[VoiceConversation] No speech detected, restarting listener");
      transitionTo("LISTENING");
      startSTT();
      return;
    }

    // Real error — show it
    transitionTo("ERROR", errorMsg);
    notificationError();
    consecutiveErrorRef.current++;
    if (consecutiveErrorRef.current >= MAX_CONSECUTIVE_ERRORS) {
      deactivate();
    }
  }, [sttError, transitionTo, deactivate, startSTT]);

  // STT completed → send via normal chat flow, or restart if nothing was captured
  useEffect(() => {
    if (voiceStateRef.current !== "LISTENING") return;
    if (!sttIsListening && isActiveRef.current) {
      if (sttTranscript) {
        // Got a transcript — submit it
        const text = sttTranscript;
        sttReset();
        submitTranscript(text);
      } else {
        // STT ended silently (no transcript, no error) — iOS stopped on its own.
        // Just restart the listener so it keeps going until user presses the button.
        console.log("[VoiceConversation] STT ended with no transcript, restarting");
        sttReset();
        startSTT();
      }
    }
  }, [sttIsListening, sttTranscript, sttReset, submitTranscript, startSTT]);

  // -- Voice interrupt: detect speech during TTS playback --

  // If user speaks during SPEAKING, interrupt TTS and switch to LISTENING
  useEffect(() => {
    if (voiceStateRef.current !== "SPEAKING" || !isActiveRef.current) return;

    // Check if STT captured real speech (not just noise)
    const speech = sttPartial || sttTranscript;
    if (speech && speech.trim().length >= MIN_TRANSCRIPT_LENGTH) {
      console.log("[VoiceConversation] Voice interrupt detected:", speech.trim());
      tts.interrupt();
      const text = (sttTranscript || sttPartial || "").trim();
      sttReset();
      hasSentRef.current = false;
      transitionTo("LISTENING");
      if (text.length >= MIN_TRANSCRIPT_LENGTH) {
        submitTranscript(text);
      } else {
        startSTT();
      }
    }
  }, [sttPartial, sttTranscript, tts, transitionTo, sttReset, submitTranscript, startSTT]);

  // Silently restart STT if it ends during SPEAKING (no speech = keep listening)
  useEffect(() => {
    if (voiceStateRef.current !== "SPEAKING" || !isActiveRef.current) return;
    if (suppressSttRestartRef.current) return; // Don't restart before the 750ms delay
    if (!sttIsListening && !sttTranscript) {
      sttReset();
      sttStart().catch(() => {});
    }
  }, [sttIsListening, sttTranscript, sttReset, sttStart]);

  // Silently handle STT errors during SPEAKING (just restart)
  useEffect(() => {
    if (voiceStateRef.current !== "SPEAKING" || !isActiveRef.current) return;
    if (suppressSttRestartRef.current) return; // Don't restart before the 750ms delay
    if (sttError) {
      sttReset();
      sttStart().catch(() => {});
    }
  }, [sttError, sttReset, sttStart]);

  // -- Effect: Watch messages for new assistant responses → auto-play TTS --
  useEffect(() => {
    if (!isActiveRef.current) return;

    const lastAssistant = findLastAssistantMessage(messages);
    if (!lastAssistant) return;

    // Skip if we've already seen this message
    if (lastAssistant.id === lastSeenAssistantIdRef.current) return;

    // Skip pending messages (still being generated)
    if (lastAssistant.isPending) return;

    // New assistant message detected — mark as seen
    lastSeenAssistantIdRef.current = lastAssistant.id;

    // If user is mid-speech, capture and send before switching to TTS
    if (voiceStateRef.current === "LISTENING") {
      const inProgressText = (sttPartialRef.current || sttTranscriptRef.current || "").trim();
      if (inProgressText.length >= MIN_TRANSCRIPT_LENGTH && !hasSentRef.current) {
        hasSentRef.current = true;
        onSendRef.current(inProgressText);
      }
    }

    // Stop listening and play TTS — use allowsRecording so iOS keeps the mic
    // active in .playAndRecord mode, enabling voice-interrupt during playback
    console.log("[VoiceConversation] New assistant message detected, playing TTS:", lastAssistant.id);
    // Suppress the auto-restart effect so sttStop() doesn't immediately restart STT
    suppressSttRestartRef.current = true;
    sttStop();
    transitionTo("SPEAKING");
    tts.play(lastAssistant.id, { allowsRecording: true });

    // Start STT for voice interrupt detection — short delay to avoid
    // picking up TTS start audio as speech
    voiceInterruptTimerRef.current = setTimeout(() => {
      suppressSttRestartRef.current = false;
      if (voiceStateRef.current === "SPEAKING" && isActiveRef.current) {
        sttReset();
        sttStart().catch(() => {});
      }
    }, 750);
  }, [messages, sttStop, sttStart, sttReset, transitionTo, tts]);

  // AppState: pause on background, auto-resume on foreground
  useEffect(() => {
    let wasBackgrounded = false;
    const sub = AppState.addEventListener("change", (state) => {
      if (state !== "active" && isActiveRef.current) {
        // Stop active operations but keep voice mode active
        wasBackgrounded = true;
        sttStop();
        tts.interrupt();
        if (voiceStateRef.current === "LISTENING" || voiceStateRef.current === "SPEAKING") {
          transitionTo("IDLE");
        }
      } else if (state === "active" && wasBackgrounded && isActiveRef.current) {
        wasBackgrounded = false;
        // Auto-resume listening when returning to the app
        if (voiceStateRef.current === "IDLE") {
          transitionTo("LISTENING");
          startSTT();
        }
      }
    });
    return () => sub.remove();
  }, [sttStop, tts, transitionTo, startSTT]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimeouts();
      sttStop();
    };
  }, [clearTimeouts, sttStop]);

  return {
    isActive,
    voiceState,
    sttPartial,
    errorMessage,
    activate,
    deactivate,
    startListening,
    sendNow,
    retry,
    interrupt,
  };
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function findLastAssistantMessage(messages: DisplayMessage[]): DisplayMessage | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") return messages[i];
  }
  return null;
}
