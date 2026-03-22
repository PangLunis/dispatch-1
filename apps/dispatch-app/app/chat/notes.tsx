import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Stack, useLocalSearchParams } from "expo-router";
import { getChatNotes, updateChatNotes } from "@/src/api/notes";
import { relativeTime } from "@/src/utils/time";

const MAX_NOTES_LENGTH = 50_000;
const WARN_THRESHOLD = 45_000;
const DEBOUNCE_MS = 1_000;

export default function ChatNotesScreen() {
  const { id, chatTitle } = useLocalSearchParams<{
    id: string;
    chatTitle?: string;
  }>();

  const [content, setContent] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);

  const pendingContentRef = useRef<string | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // Load notes on mount
  useEffect(() => {
    mountedRef.current = true;
    (async () => {
      try {
        const notes = await getChatNotes(id ?? "");
        if (mountedRef.current) {
          setContent(notes.content);
          setUpdatedAt(notes.updated_at);
        }
      } catch {
        // Empty notes is fine
      } finally {
        if (mountedRef.current) setIsLoading(false);
      }
    })();

    return () => {
      mountedRef.current = false;
    };
  }, [id]);

  // Save function
  const saveNotes = useCallback(
    async (text: string) => {
      if (!id) return;
      setIsSaving(true);
      setSaveError(false);
      try {
        const result = await updateChatNotes(id, text);
        if (mountedRef.current) {
          setUpdatedAt(result.updated_at);
          setSaveError(false);
        }
      } catch {
        if (mountedRef.current) setSaveError(true);
      } finally {
        if (mountedRef.current) setIsSaving(false);
      }
    },
    [id],
  );

  // Flush pending save on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      if (pendingContentRef.current !== null) {
        // Fire final save (fire-and-forget since we're unmounting)
        const finalContent = pendingContentRef.current;
        pendingContentRef.current = null;
        if (id) {
          updateChatNotes(id, finalContent).catch(() => {});
        }
      }
    };
  }, [id]);

  const handleChange = useCallback(
    (text: string) => {
      if (text.length > MAX_NOTES_LENGTH) {
        text = text.slice(0, MAX_NOTES_LENGTH);
      }
      setContent(text);
      pendingContentRef.current = text;

      // Debounce save
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        pendingContentRef.current = null;
        saveNotes(text);
      }, DEBOUNCE_MS);
    },
    [saveNotes],
  );

  const showCharCount = content.length >= WARN_THRESHOLD;

  return (
    <>
      <Stack.Screen
        options={{
          title: chatTitle ? `Notes — ${chatTitle}` : "Notes",
          headerStyle: { backgroundColor: "#09090b" },
          headerTintColor: "#fafafa",
          headerShadowVisible: false,
        }}
      />
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
      >
        {/* Status bar at top */}
        <View style={styles.statusBar}>
          <View style={styles.statusBarLeft}>
            {saveError ? (
              <Text style={styles.errorText}>Unsaved changes</Text>
            ) : isSaving ? (
              <Text style={styles.savingText}>Saving...</Text>
            ) : updatedAt ? (
              <Text style={styles.timestampText}>
                Last edited {relativeTime(updatedAt)}
              </Text>
            ) : null}
          </View>
          {showCharCount && (
            <Text
              style={[
                styles.charCount,
                content.length >= MAX_NOTES_LENGTH && styles.charCountLimit,
              ]}
            >
              {content.length.toLocaleString()}/{MAX_NOTES_LENGTH.toLocaleString()}
            </Text>
          )}
        </View>

        {isLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator color="#71717a" size="small" />
          </View>
        ) : (
          <TextInput
            style={styles.editor}
            value={content}
            onChangeText={handleChange}
            placeholder="Add notes for this chat..."
            placeholderTextColor="#52525b"
            multiline
            autoFocus
            textAlignVertical="top"
            maxLength={MAX_NOTES_LENGTH}
          />
        )}
      </KeyboardAvoidingView>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  loadingContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
  },
  editor: {
    flex: 1,
    color: "#fafafa",
    fontSize: 16,
    lineHeight: 24,
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 16,
  },
  statusBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  statusBarLeft: {
    flex: 1,
  },
  timestampText: {
    color: "#71717a",
    fontSize: 12,
  },
  savingText: {
    color: "#a1a1aa",
    fontSize: 12,
  },
  errorText: {
    color: "#ef4444",
    fontSize: 12,
  },
  charCount: {
    color: "#71717a",
    fontSize: 12,
  },
  charCountLimit: {
    color: "#ef4444",
  },
});
