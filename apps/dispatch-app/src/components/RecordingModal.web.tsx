import React, { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { TranscriptionView } from "./TranscriptionView";
import { branding } from "../config/branding";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_DURATION_SECONDS = 120;

// ---------------------------------------------------------------------------
// Props — same interface as native RecordingModal
// ---------------------------------------------------------------------------

interface RecordingModalProps {
  visible: boolean;
  onClose: () => void;
  onSend: (transcript: string) => void;
}

// ---------------------------------------------------------------------------
// Timer formatting
// ---------------------------------------------------------------------------

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RecordingModal({
  visible,
  onClose,
  onSend,
}: RecordingModalProps) {
  const speech = useSpeechRecognition();
  const [duration, setDuration] = useState(0);
  const [hasStopped, setHasStopped] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const displayText = speech.isListening
    ? speech.partialTranscript || speech.transcript
    : speech.transcript;

  // -------------------------------------------------------------------------
  // Auto-start recording when modal becomes visible
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (visible) {
      setDuration(0);
      setHasStopped(false);
      speech.reset();
      speech.start();
    } else {
      if (speech.isListening) {
        speech.cancel();
      }
      stopTimer();
      setDuration(0);
      setHasStopped(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // -------------------------------------------------------------------------
  // Duration timer
  // -------------------------------------------------------------------------

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startTimer = useCallback(() => {
    if (timerRef.current) return;
    timerRef.current = setInterval(() => {
      setDuration((prev) => {
        const next = prev + 1;
        if (next >= MAX_DURATION_SECONDS) {
          speech.stop();
          setHasStopped(true);
          stopTimer();
        }
        return next;
      });
    }, 1000);
  }, [speech, stopTimer]);

  useEffect(() => {
    if (speech.isListening) {
      startTimer();
    } else {
      stopTimer();
    }
  }, [speech.isListening, startTimer, stopTimer]);

  useEffect(() => {
    return () => stopTimer();
  }, [stopTimer]);

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  const handleCancel = useCallback(() => {
    speech.cancel();
    stopTimer();
    onClose();
  }, [speech, stopTimer, onClose]);

  const handleStop = useCallback(() => {
    speech.stop();
    setHasStopped(true);
    stopTimer();
  }, [speech, stopTimer]);

  const handleDiscard = useCallback(() => {
    speech.reset();
    onClose();
  }, [speech, onClose]);

  const handleSend = useCallback(() => {
    const text = speech.transcript.trim();
    if (!text) return;
    onSend(text);
    speech.reset();
    onClose();
  }, [speech, onSend, onClose]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (!visible) return null;

  const isRecording = speech.isListening;
  const canSend = speech.transcript.trim().length > 0;

  return (
    <View style={styles.backdrop}>
      <Pressable style={styles.backdropPressable} onPress={handleCancel} />
      <View style={styles.sheet}>
        {/* Transcription area */}
        <View style={styles.transcriptionArea}>
          <TranscriptionView
            displayText={displayText}
            isListening={isRecording}
          />
        </View>

        {/* Controls */}
        {isRecording ? (
          <View style={styles.controlsRow}>
            <Pressable
              style={styles.cancelButton}
              onPress={handleCancel}
            >
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>

            <View style={styles.timerContainer}>
              <View style={styles.redDot} />
              <Text style={styles.timerText}>
                {formatDuration(duration)}
              </Text>
            </View>

            <Pressable style={styles.stopButton} onPress={handleStop}>
              <View style={styles.stopSquare} />
            </Pressable>
          </View>
        ) : hasStopped ? (
          <View style={styles.stoppedContainer}>
            <Text style={styles.readyLabel}>Ready to send</Text>
            <View style={styles.controlsRow}>
              <Pressable
                style={styles.discardButton}
                onPress={handleDiscard}
              >
                <Text style={styles.discardText}>Discard</Text>
              </Pressable>

              <Pressable
                style={[
                  styles.sendButton,
                  !canSend && styles.sendButtonDisabled,
                ]}
                onPress={handleSend}
                disabled={!canSend}
              >
                <Text
                  style={[
                    styles.sendText,
                    !canSend && styles.sendTextDisabled,
                  ]}
                >
                  Send
                </Text>
              </Pressable>
            </View>
          </View>
        ) : (
          <View style={styles.controlsRow}>
            <Pressable
              style={styles.cancelButton}
              onPress={handleCancel}
            >
              <Text style={styles.cancelText}>Close</Text>
            </Pressable>
            {speech.error && (
              <Text style={styles.errorText}>{speech.error}</Text>
            )}
          </View>
        )}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles — CSS-like for web, using RN StyleSheet
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  backdrop: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(0, 0, 0, 0.6)",
    justifyContent: "flex-end",
    zIndex: 1000,
  },
  backdropPressable: {
    flex: 1,
  },
  sheet: {
    backgroundColor: "#18181b",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingTop: 16,
    paddingBottom: 32,
    paddingHorizontal: 20,
    minHeight: 220,
  },
  transcriptionArea: {
    marginBottom: 20,
    paddingHorizontal: 4,
  },
  controlsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 8,
  },
  cancelButton: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    cursor: "pointer" as any,
  },
  cancelText: {
    color: "#a1a1aa",
    fontSize: 16,
  },
  timerContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  redDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#ef4444",
  },
  timerText: {
    color: "#fafafa",
    fontSize: 16,
    fontVariant: ["tabular-nums"],
    minWidth: 40,
  },
  stopButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#ef4444",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer" as any,
  },
  stopSquare: {
    width: 16,
    height: 16,
    borderRadius: 3,
    backgroundColor: "#ffffff",
  },
  stoppedContainer: {
    alignItems: "center",
    gap: 16,
  },
  readyLabel: {
    color: "#a1a1aa",
    fontSize: 14,
  },
  discardButton: {
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "#3f3f46",
    cursor: "pointer" as any,
  },
  discardText: {
    color: "#a1a1aa",
    fontSize: 16,
  },
  sendButton: {
    paddingVertical: 12,
    paddingHorizontal: 32,
    borderRadius: 22,
    backgroundColor: branding.accentColor,
    cursor: "pointer" as any,
  },
  sendButtonDisabled: {
    opacity: 0.4,
  },
  sendText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "600",
  },
  sendTextDisabled: {
    opacity: 0.6,
  },
  errorText: {
    color: "#ef4444",
    fontSize: 14,
    flex: 1,
    textAlign: "center",
    marginHorizontal: 12,
  },
});
