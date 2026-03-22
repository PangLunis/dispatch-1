import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { markAgentSessionAsRead } from "@/src/state/unreadAgents";
import {
  agentAdapter,
  useMessages,
  type DisplayMessage,
} from "@/src/hooks/useMessages";
import { MessageBubble } from "@/src/components/MessageBubble";
import { SdkEventBubble } from "@/src/components/SdkEventBubble";
import { InputBar } from "@/src/components/InputBar";
import { ThinkingIndicator } from "@/src/components/ThinkingIndicator";
import { EmptyState } from "@/src/components/EmptyState";
import { SourceBadge } from "@/src/components/SourceBadge";
import { branding } from "@/src/config/branding";
import { screenStyles } from "@/src/styles/shared";
import {
  deleteAgentSession,
  renameAgentSession,
} from "@/src/api/agents";
import {
  showAlert,
  showDestructiveConfirm,
  showPrompt,
} from "@/src/utils/alert";
import { useSdkEvents } from "@/src/hooks/useSdkEvents";
import type { SdkEvent } from "@/src/api/types";

export default function AgentConversationScreen() {
  const router = useRouter();
  const { id, sessionName, sessionSource, sessionType } =
    useLocalSearchParams<{
      id: string;
      sessionName?: string;
      sessionSource?: string;
      sessionType?: string;
    }>();

  const [currentName, setCurrentName] = useState(sessionName || id || "Agent");
  const [sdkMode, setSdkMode] = useState(false);
  const isDispatchApi = sessionType === "dispatch-api";

  // Mark this agent session as read when opened
  useEffect(() => {
    if (id) markAgentSessionAsRead(id);
  }, [id]);

  const adapter = useMemo(() => agentAdapter(id ?? ""), [id]);
  const { messages, isLoading, error, isThinking, sendMessage } =
    useMessages(adapter, id ? `agent:${id}` : undefined);

  const {
    events: sdkEvents,
    isLoading: sdkLoading,
    error: sdkError,
    isComplete: sdkComplete,
  } = useSdkEvents(id ?? "", sdkMode || isThinking);

  // Hide thinking immediately when SDK events report turn complete
  const showThinking = isThinking && !sdkComplete;

  // Inverted FlatList: reverse data so newest at bottom
  const invertedMessages = useMemo(
    () => [...messages].reverse(),
    [messages],
  );

  const invertedSdkEvents = useMemo(
    () => [...sdkEvents].reverse(),
    [sdkEvents],
  );

  const handleSend = useCallback(
    (text: string) => {
      sendMessage(text);
    },
    [sendMessage],
  );

  // -----------------------------------------------------------------------
  // Rename (dispatch-api sessions only)
  // -----------------------------------------------------------------------

  const handleRename = useCallback(async () => {
    if (!id) return;

    const name = await showPrompt("Rename Session", "Enter a new name:", currentName);
    if (!name) return;

    try {
      await renameAgentSession(id, name);
      setCurrentName(name);
    } catch {
      showAlert("Error", "Failed to rename session");
    }
  }, [id, currentName]);

  // -----------------------------------------------------------------------
  // Delete (dispatch-api sessions only)
  // -----------------------------------------------------------------------

  const handleDelete = useCallback(async () => {
    if (!id) return;

    const confirmed = await showDestructiveConfirm(
      "Delete Session",
      `Delete "${currentName}"? This cannot be undone.`,
      "Delete",
    );
    if (!confirmed) return;

    try {
      await deleteAgentSession(id, true);
      router.back();
    } catch {
      showAlert("Error", "Failed to delete session");
    }
  }, [id, currentName, router]);

  // -----------------------------------------------------------------------
  // Render messages — reuse MessageBubble (no audioState = no audio controls)
  // -----------------------------------------------------------------------

  const renderMessageItem = useCallback(
    ({ item }: { item: DisplayMessage }) => (
      <MessageBubble message={item} />
    ),
    [],
  );

  const renderSdkItem = useCallback(
    ({ item }: { item: SdkEvent }) => <SdkEventBubble event={item} />,
    [],
  );

  const messageKeyExtractor = useCallback((item: DisplayMessage) => item.id, []);
  const sdkKeyExtractor = useCallback((item: SdkEvent) => String(item.id), []);


  // -----------------------------------------------------------------------
  // Header right buttons
  // -----------------------------------------------------------------------

  const headerRight = useCallback(() => {
    if (!isDispatchApi) return null;
    return (
      <View style={headerStyles.rightContainer}>
        <Pressable onPress={handleRename} hitSlop={8} style={headerStyles.button}>
          <Text style={headerStyles.buttonText}>Rename</Text>
        </Pressable>
        <Pressable onPress={handleDelete} hitSlop={8} style={headerStyles.button}>
          <Text style={headerStyles.deleteText}>Delete</Text>
        </Pressable>
      </View>
    );
  }, [isDispatchApi, handleRename, handleDelete]);

  // -----------------------------------------------------------------------
  // Header title with badges
  // -----------------------------------------------------------------------

  const headerTitle = useCallback(() => {
    return (
      <View style={headerStyles.titleContainer}>
        <Text style={headerStyles.title} numberOfLines={1}>
          {currentName}
        </Text>
        {sessionSource ? (
          <View style={headerStyles.badges}>
            <SourceBadge source={sessionSource} />
          </View>
        ) : null}
      </View>
    );
  }, [currentName, sessionSource]);

  // -----------------------------------------------------------------------
  // Content rendering based on mode
  // -----------------------------------------------------------------------

  const activeLoading = sdkMode ? sdkLoading : isLoading;
  const activeError = sdkMode ? sdkError : error;
  const hasData = sdkMode ? sdkEvents.length > 0 : messages.length > 0;

  return (
    <>
      <Stack.Screen
        options={{
          headerTitle,
          headerBackTitle: "Sessions",
          headerRight,
          headerStyle: { backgroundColor: "#09090b" },
          headerTintColor: "#fafafa",
          headerShadowVisible: false,
        }}
      />
      <KeyboardAvoidingView
        style={screenStyles.container}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
      >
        <View style={toggleStyles.modeToggle}>
          <Pressable
            onPress={() => setSdkMode(false)}
            style={[
              toggleStyles.modeButton,
              !sdkMode && toggleStyles.modeButtonActive,
            ]}
          >
            <Text
              style={[
                toggleStyles.modeButtonText,
                !sdkMode && toggleStyles.modeButtonTextActive,
              ]}
            >
              Messages
            </Text>
          </Pressable>
          <Pressable
            onPress={() => setSdkMode(true)}
            style={[
              toggleStyles.modeButton,
              sdkMode && toggleStyles.modeButtonActive,
            ]}
          >
            <Text
              style={[
                toggleStyles.modeButtonText,
                sdkMode && toggleStyles.modeButtonTextActive,
              ]}
            >
              SDK Events
            </Text>
          </Pressable>
        </View>

        {activeLoading ? (
          <View style={screenStyles.loadingContainer}>
            <ActivityIndicator color="#71717a" size="small" />
          </View>
        ) : activeError && !hasData ? (
          <View style={screenStyles.errorContainer}>
            <Text style={screenStyles.errorText}>{activeError}</Text>
          </View>
        ) : !hasData ? (
          <EmptyState
            title={sdkMode ? "No SDK events" : "No messages yet"}
            subtitle={
              sdkMode
                ? "SDK events will appear here when the agent is active"
                : "Send a message to start the conversation"
            }
            icon={sdkMode ? "⚡" : "💬"}
          />
        ) : sdkMode ? (
          <FlatList
            data={invertedSdkEvents}
            inverted
            renderItem={renderSdkItem}
            keyExtractor={sdkKeyExtractor}
            contentContainerStyle={screenStyles.messageList}
            showsVerticalScrollIndicator={false}
            keyboardDismissMode="interactive"
            keyboardShouldPersistTaps="handled"
          />
        ) : (
          <FlatList
            data={invertedMessages}
            inverted
            renderItem={renderMessageItem}
            keyExtractor={messageKeyExtractor}
            contentContainerStyle={screenStyles.messageList}
            showsVerticalScrollIndicator={false}
            keyboardDismissMode="interactive"
            keyboardShouldPersistTaps="handled"
          />
        )}
        {showThinking && <ThinkingIndicator events={sdkEvents} />}
        {isDispatchApi ? (
          <InputBar onSend={handleSend} />
        ) : (
          <View style={readOnlyStyles.footer}>
            <Text style={readOnlyStyles.footerText}>
              Managed by agent — reply via {sessionSource === "signal" ? "Signal" : "iMessage"}
            </Text>
          </View>
        )}
      </KeyboardAvoidingView>
    </>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const headerStyles = StyleSheet.create({
  titleContainer: {
    alignItems: "center",
    gap: 4,
  },
  title: {
    color: "#fafafa",
    fontSize: 16,
    fontWeight: "600",
  },
  badges: {
    flexDirection: "row",
    gap: 6,
  },
  rightContainer: {
    flexDirection: "row",
    gap: 12,
  },
  button: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  buttonText: {
    color: branding.accentColor,
    fontSize: 14,
    fontWeight: "500",
  },
  deleteText: {
    color: "#ef4444",
    fontSize: 14,
    fontWeight: "500",
  },
});

const readOnlyStyles = StyleSheet.create({
  footer: {
    backgroundColor: "#18181b",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#27272a",
    paddingHorizontal: 16,
    paddingVertical: 12,
    alignItems: "center",
  },
  footerText: {
    color: "#52525b",
    fontSize: 13,
    fontStyle: "italic",
  },
});

const toggleStyles = StyleSheet.create({
  modeToggle: {
    flexDirection: "row",
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  modeButton: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: "#18181b",
  },
  modeButtonActive: {
    backgroundColor: "#3f3f46",
  },
  modeButtonText: {
    color: "#71717a",
    fontSize: 13,
    fontWeight: "600",
  },
  modeButtonTextActive: {
    color: "#fafafa",
  },
});
