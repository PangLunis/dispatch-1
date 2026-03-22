import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Animated,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { RecordingIndicator } from "./RecordingIndicator";
import { TranscriptionView } from "./TranscriptionView";
import { branding } from "../config/branding";
import {
  impactLight,
  impactMedium,
  notificationSuccess,
} from "../utils/haptics";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_DURATION_SECONDS = 120;

// ---------------------------------------------------------------------------
// Props
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
  const slideAnim = useRef(new Animated.Value(300)).current;

  // The text to display — show partial while listening, final when stopped
  const displayText = speech.isListening
    ? speech.partialTranscript || speech.transcript
    : speech.transcript;

  // -------------------------------------------------------------------------
  // Slide animation
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (visible) {
      Animated.spring(slideAnim, {
        toValue: 0,
        useNativeDriver: true,
        tension: 65,
        friction: 11,
      }).start();
    } else {
      slideAnim.setValue(300);
    }
  }, [visible, slideAnim]);

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
      // Cleanup when closing
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

  const startTimer = useCallback(() => {
    if (timerRef.current) return;
    timerRef.current = setInterval(() => {
      setDuration((prev) => {
        const next = prev + 1;
        if (next >= MAX_DURATION_SECONDS) {
          // Auto-stop at max duration
          speech.stop();
          setHasStopped(true);
          stopTimer();
          impactMedium();
        }
        return next;
      });
    }, 1000);
  }, [speech]);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Start/stop timer based on listening state
  useEffect(() => {
    if (speech.isListening) {
      startTimer();
    } else {
      stopTimer();
    }
  }, [speech.isListening, startTimer, stopTimer]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => stopTimer();
  }, [stopTimer]);

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  const handleCancel = useCallback(() => {
    impactLight();
    speech.cancel();
    stopTimer();
    onClose();
  }, [speech, stopTimer, onClose]);

  const handleStop = useCallback(() => {
    impactMedium();
    speech.stop();
    setHasStopped(true);
    stopTimer();
  }, [speech, stopTimer]);

  const handleDiscard = useCallback(() => {
    impactLight();
    speech.reset();
    onClose();
  }, [speech, onClose]);

  const handleSend = useCallback(() => {
    const text = speech.transcript.trim();
    if (!text) return;
    notificationSuccess();
    onSend(text);
    speech.reset();
    onClose();
  }, [speech, onSend, onClose]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const isRecording = speech.isListening;
  const canSend = speech.transcript.trim().length > 0;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={handleCancel}
    >
      <Pressable style={styles.backdrop} onPress={handleCancel}>
        <Animated.View
          style={[
            styles.sheet,
            { transform: [{ translateY: slideAnim }] },
          ]}
        >
          {/* Prevent backdrop press from closing when tapping the sheet */}
          <Pressable onPress={undefined}>
            {/* Transcription area */}
            <View style={styles.transcriptionArea}>
              <TranscriptionView
                displayText={displayText}
                isListening={isRecording}
              />
            </View>

            {/* Controls */}
            {isRecording ? (
              // Recording state
              <View style={styles.controlsRow}>
                <Pressable
                  style={styles.cancelButton}
                  onPress={handleCancel}
                  hitSlop={12}
                >
                  <Text style={styles.cancelText}>Cancel</Text>
                </Pressable>

                <View style={styles.timerContainer}>
                  <View style={styles.redDot} />
                  <RecordingIndicator isActive={true} />
                  <Text style={styles.timerText}>
                    {formatDuration(duration)}
                  </Text>
                </View>

                <Pressable
                  style={styles.stopButton}
                  onPress={handleStop}
                  hitSlop={12}
                >
                  <View style={styles.stopSquare} />
                </Pressable>
              </View>
            ) : hasStopped ? (
              // Stopped state — ready to send
              <View style={styles.stoppedContainer}>
                <Text style={styles.readyLabel}>Ready to send</Text>
                <View style={styles.controlsRow}>
                  <Pressable
                    style={styles.discardButton}
                    onPress={handleDiscard}
                    hitSlop={12}
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
                    hitSlop={12}
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
              // Error or initial state
              <View style={styles.controlsRow}>
                <Pressable
                  style={styles.cancelButton}
                  onPress={handleCancel}
                  hitSlop={12}
                >
                  <Text style={styles.cancelText}>Close</Text>
                </Pressable>
                {speech.error && (
                  <Text style={styles.errorText}>{speech.error}</Text>
                )}
              </View>
            )}
          </Pressable>
        </Animated.View>
      </Pressable>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.6)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: "#18181b",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingTop: 16,
    paddingBottom: 40,
    paddingHorizontal: 20,
    minHeight: 240,
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
