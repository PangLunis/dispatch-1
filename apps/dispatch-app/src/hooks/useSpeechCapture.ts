import { useCallback, useRef, useState } from "react";
import {
  ExpoSpeechRecognitionModule,
  useSpeechRecognitionEvent,
} from "@jamsch/expo-speech-recognition";
import { impactMedium, notificationError } from "../utils/haptics";

export interface SpeechCaptureState {
  isListening: boolean;
  transcript: string;
  partial: string;
  error: string | null;
}

export interface SpeechCaptureActions {
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

/**
 * Low-level speech capture hook that uses ExpoSpeechRecognitionModule directly.
 *
 * Unlike useSpeechRecognition (shared hook), this uses a guard ref so events
 * from other hook instances (e.g., InputBar's) are ignored. This avoids the
 * global singleton conflict where multiple useSpeechRecognitionEvent listeners
 * all receive events from the same native module.
 */
interface SpeechCaptureOptions {
  /** Strings the recognizer should bias toward (e.g., app name) */
  contextualStrings?: string[];
}

export function useSpeechCapture(options: SpeechCaptureOptions = {}): SpeechCaptureState & SpeechCaptureActions {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [partial, setPartial] = useState("");
  const [error, setError] = useState<string | null>(null);

  const accumulatedRef = useRef("");
  const activeRef = useRef(false);
  const startingRef = useRef(false);
  const contextualStringsRef = useRef(options.contextualStrings || []);
  contextualStringsRef.current = options.contextualStrings || [];

  // -- Event handlers (guarded by activeRef) --

  useSpeechRecognitionEvent("start", () => {
    if (!activeRef.current) return;
    setIsListening(true);
    setError(null);
    startingRef.current = false;
  });

  useSpeechRecognitionEvent("end", () => {
    if (!activeRef.current) return;
    setIsListening(false);
    setPartial("");
  });

  useSpeechRecognitionEvent("result", (event) => {
    if (!activeRef.current) return;
    const results = event.results;
    if (!results || results.length === 0) return;
    const best = results[0].transcript;
    if (!best) return;

    if (event.isFinal) {
      const sep = accumulatedRef.current ? " " : "";
      accumulatedRef.current += sep + best;
      setTranscript(accumulatedRef.current);
      setPartial("");
    } else {
      const sep = accumulatedRef.current ? " " : "";
      setPartial(accumulatedRef.current + sep + best);
    }
  });

  useSpeechRecognitionEvent("error", (event) => {
    if (!activeRef.current) return;
    if (event.error === "aborted") return;
    setError(event.message || event.error || "Speech recognition error");
    setIsListening(false);
    startingRef.current = false;
  });

  // -- Actions --

  const start = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;

    setError(null);
    accumulatedRef.current = "";
    setTranscript("");
    setPartial("");
    activeRef.current = true;

    try {
      const permResult = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!permResult.granted) {
        setError("Microphone permission denied. Go to Settings > Dispatch > Microphone.");
        startingRef.current = false;
        notificationError();
        return;
      }

      // continuous: false — iOS auto-stops after a speech pause, enabling natural
      // turn-taking. The voice agent hook uses this to auto-submit when STT ends.
      ExpoSpeechRecognitionModule.start({
        lang: "en-US",
        interimResults: true,
        continuous: false,
        contextualStrings: contextualStringsRef.current,
      });

      impactMedium();
    } catch (err) {
      setError((err as Error).message || "Failed to start speech recognition");
      startingRef.current = false;
      notificationError();
    }
  }, []);

  const stop = useCallback(() => {
    try { ExpoSpeechRecognitionModule.abort(); } catch (err) { console.warn("[SpeechCapture] abort error:", err); }
    activeRef.current = false;
    startingRef.current = false;
    setIsListening(false);
    setPartial("");
  }, []);

  const reset = useCallback(() => {
    accumulatedRef.current = "";
    setTranscript("");
    setPartial("");
    setError(null);
  }, []);

  return { isListening, transcript, partial, error, start, stop, reset };
}
