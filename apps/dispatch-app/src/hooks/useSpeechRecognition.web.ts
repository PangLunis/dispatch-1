import { useCallback, useEffect, useRef, useState } from "react";
import { applyNameCorrections } from "../utils/speechCorrections";
import type { UseSpeechRecognitionReturn } from "../types/speechRecognition";

// Re-export types for consumers
export type {
  SpeechRecognitionState,
  SpeechRecognitionActions,
  UseSpeechRecognitionReturn,
} from "../types/speechRecognition";

// ---------------------------------------------------------------------------
// Web Speech API types (not in all TS libs)
// ---------------------------------------------------------------------------

type WebSpeechRecognition = typeof window extends {
  SpeechRecognition: infer T;
}
  ? T
  : unknown;

function getWebSpeechRecognition(): (new () => any) | null {
  if (typeof window === "undefined") return null;
  const W = window as any;
  return W.SpeechRecognition || W.webkitSpeechRecognition || null;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSpeechRecognition(): UseSpeechRecognitionReturn {
  const [isListening, setIsListening] = useState(false);
  const [isAvailable] = useState(() => getWebSpeechRecognition() !== null);
  const [transcript, setTranscript] = useState("");
  const [partialTranscript, setPartialTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<any>(null);
  const accumulatedRef = useRef("");

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  const start = useCallback(async () => {
    const SpeechRecognitionClass = getWebSpeechRecognition();
    if (!SpeechRecognitionClass) {
      setError("Speech recognition not available in this browser");
      return;
    }

    // Reset state
    setError(null);
    accumulatedRef.current = "";
    setTranscript("");
    setPartialTranscript("");

    const recognition = new SpeechRecognitionClass();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onend = () => {
      setIsListening(false);
      setPartialTranscript("");
      recognitionRef.current = null;
    };

    recognition.onerror = (event: any) => {
      // "aborted" errors are intentional (from cancel/stop)
      if (event.error === "aborted") return;
      setError(event.error || "Speech recognition error");
      setIsListening(false);
    };

    recognition.onresult = (event: any) => {
      let finalText = "";
      let interimText = "";

      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0]?.transcript || "";
        if (result.isFinal) {
          finalText += text;
        } else {
          interimText += text;
        }
      }

      if (finalText) {
        const corrected = applyNameCorrections(finalText);
        const separator = accumulatedRef.current ? " " : "";
        accumulatedRef.current += separator + corrected;
        setTranscript(accumulatedRef.current);
      }

      if (interimText) {
        const corrected = applyNameCorrections(interimText);
        const separator = accumulatedRef.current ? " " : "";
        setPartialTranscript(accumulatedRef.current + separator + corrected);
      } else {
        setPartialTranscript("");
      }
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, []);

  const stop = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  }, []);

  const cancel = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.abort();
      recognitionRef.current = null;
    }
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
