import { useCallback, useRef, useState } from "react";
import {
  ExpoSpeechRecognitionModule,
  useSpeechRecognitionEvent,
} from "@jamsch/expo-speech-recognition";
import { applyNameCorrections } from "../utils/speechCorrections";
import { branding } from "../config/branding";
import type { UseSpeechRecognitionReturn } from "../types/speechRecognition";

// Re-export types for consumers
export type {
  SpeechRecognitionState,
  SpeechRecognitionActions,
  UseSpeechRecognitionReturn,
} from "../types/speechRecognition";

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSpeechRecognition(): UseSpeechRecognitionReturn {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [partialTranscript, setPartialTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Track accumulated final results across multiple recognition events
  const accumulatedRef = useRef("");

  // Native speech recognition is always available on iOS
  const isAvailable = true;

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  useSpeechRecognitionEvent("start", () => {
    setIsListening(true);
    setError(null);
  });

  useSpeechRecognitionEvent("end", () => {
    setIsListening(false);
    setPartialTranscript("");
  });

  useSpeechRecognitionEvent("result", (event) => {
    // event.results is an array of alternatives for the current result
    // event.isFinal indicates whether this is a final or interim result
    const results = event.results;
    if (!results || results.length === 0) return;

    const bestTranscript = results[0].transcript;
    if (!bestTranscript) return;

    const corrected = applyNameCorrections(bestTranscript);

    if (event.isFinal) {
      // Append to accumulated transcript
      const separator = accumulatedRef.current ? " " : "";
      accumulatedRef.current += separator + corrected;
      setTranscript(accumulatedRef.current);
      setPartialTranscript("");
    } else {
      // Show as partial / interim result
      const separator = accumulatedRef.current ? " " : "";
      setPartialTranscript(accumulatedRef.current + separator + corrected);
    }
  });

  useSpeechRecognitionEvent("error", (event) => {
    // "aborted" errors are intentional (from cancel)
    if (event.error === "aborted") return;
    setError(event.message || event.error || "Speech recognition error");
    setIsListening(false);
  });

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const start = useCallback(async () => {
    setError(null);
    accumulatedRef.current = "";
    setTranscript("");
    setPartialTranscript("");

    // Request permission if needed
    const permResult =
      await ExpoSpeechRecognitionModule.requestPermissionsAsync();
    if (!permResult.granted) {
      setError("Microphone permission denied");
      return;
    }

    ExpoSpeechRecognitionModule.start({
      lang: "en-US",
      interimResults: true,
      continuous: true,
      contextualStrings: [branding.displayName],
    });
  }, []);

  const stop = useCallback(() => {
    ExpoSpeechRecognitionModule.stop();
  }, []);

  const cancel = useCallback(() => {
    ExpoSpeechRecognitionModule.abort();
    accumulatedRef.current = "";
    setTranscript("");
    setPartialTranscript("");
    setIsListening(false);
  }, []);

  const reset = useCallback(() => {
    accumulatedRef.current = "";
    setTranscript("");
    setPartialTranscript("");
    setError(null);
  }, []);

  return {
    isListening,
    isAvailable,
    transcript,
    partialTranscript,
    error,
    start,
    stop,
    cancel,
    reset,
  };
}
