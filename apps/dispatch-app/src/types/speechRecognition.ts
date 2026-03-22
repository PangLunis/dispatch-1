/**
 * Shared types for speech recognition hooks.
 * Both native (.ts) and web (.web.ts) implementations must conform to these.
 */

export interface SpeechRecognitionState {
  /** Whether speech recognition is actively listening */
  isListening: boolean;
  /** Whether the speech recognition API is available */
  isAvailable: boolean;
  /** Final accumulated transcript text */
  transcript: string;
  /** Interim/partial results (not yet finalized) */
  partialTranscript: string;
  /** Any error message */
  error: string | null;
}

export interface SpeechRecognitionActions {
  start: () => Promise<void>;
  stop: () => void;
  cancel: () => void;
  /** Reset transcript state without stopping */
  reset: () => void;
}

export type UseSpeechRecognitionReturn = SpeechRecognitionState &
  SpeechRecognitionActions;
