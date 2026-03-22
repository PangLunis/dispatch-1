import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

interface TranscriptionViewProps {
  /** Final + partial combined display text */
  displayText: string;
  /** Whether speech recognition is actively listening */
  isListening: boolean;
}

/**
 * Displays live transcription text with a "Listening..." placeholder
 * when no text has been captured yet.
 */
export function TranscriptionView({
  displayText,
  isListening,
}: TranscriptionViewProps) {
  const hasText = displayText.trim().length > 0;

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {hasText ? (
          <Text style={styles.transcriptText}>{displayText}</Text>
        ) : isListening ? (
          <Text style={styles.placeholderText}>Listening...</Text>
        ) : (
          <Text style={styles.placeholderText}>
            Tap the mic to start recording
          </Text>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    minHeight: 80,
    maxHeight: 160,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingVertical: 8,
    paddingHorizontal: 4,
  },
  transcriptText: {
    color: "#fafafa",
    fontSize: 16,
    lineHeight: 24,
  },
  placeholderText: {
    color: "#71717a",
    fontSize: 16,
    lineHeight: 24,
    fontStyle: "italic",
  },
});
