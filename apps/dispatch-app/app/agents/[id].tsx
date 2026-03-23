import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  InteractionManager,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { SymbolView } from "expo-symbols";
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
  forkAgentToChat,
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
  const { id, sessionName, sessionSource, sessionType, backTitle } =
    useLocalSearchParams<{
      id: string;
      sessionName?: string;
      sessionSource?: string;
      sessionType?: string;
      backTitle?: string;
    }>();

  const [currentName, setCurrentName] = useState(sessionName || id || "Agent");
  const [sdkMode, setSdkMode] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ x: 0, y: 0 });
  const [isForking, setIsForking] = useState(false);
  const menuButtonRef = useRef<View>(null);
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
  // Fork to Chat (all session types)
  // -----------------------------------------------------------------------

  const handleForkToChat = useCallback(async () => {
    if (!id) return;

    const forkTitle = await showPrompt("Fork to Chat", "Title for the new chat:", `${currentName} (fork)`);
    if (!forkTitle) return;

    setIsForking(true);
    try {
      const forked = await forkAgentToChat(id, forkTitle);
      router.push({
        pathname: "/chat/[id]",
        params: { id: forked.id, chatTitle: forked.title },
      });
    } catch (err) {
      showAlert("Error", err instanceof Error ? err.message : "Failed to fork to chat");
    } finally {
      setIsForking(false);
    }
  }, [id, currentName, router]);

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
  // Header right — ellipsis menu button
  // -----------------------------------------------------------------------

  const handleMenuPress = useCallback(() => {
    menuButtonRef.current?.measureInWindow((x, y, width, height) => {
      setMenuPosition({ x: x + width - 160, y: y + height + 8 });
      setMenuVisible(true);
    });
  }, []);

  const headerRight = useCallback(
    () => (
      <Pressable
        ref={menuButtonRef}
        onPress={handleMenuPress}
        hitSlop={8}
        style={headerStyles.menuButton}
      >
        <SymbolView
          name={{ ios: "ellipsis.circle", android: "more_vert", web: "more_vert" }}
          tintColor={branding.accentColor}
          size={22}
          weight="medium"
        />
      </Pressable>
    ),
    [handleMenuPress],
  );

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
          headerBackTitle: backTitle || "Sessions",
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

      {/* Dropdown menu */}
      <Modal
        visible={menuVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setMenuVisible(false)}
      >
        <Pressable
          style={menuStyles.overlay}
          onPress={() => setMenuVisible(false)}
        >
          <View
            style={[
              menuStyles.dropdown,
              { top: menuPosition.y, left: menuPosition.x },
            ]}
          >
            {/* Fork to Chat — available for all session types */}
            <Pressable
              style={[menuStyles.item, (isForking || messages.length === 0) && { opacity: 0.5 }]}
              disabled={isForking || messages.length === 0}
              onPress={() => {
                setMenuVisible(false);
                InteractionManager.runAfterInteractions(handleForkToChat);
              }}
            >
              <SymbolView
                name={{ ios: "arrow.triangle.branch", android: "fork_right", web: "fork_right" }}
                tintColor="#fafafa"
                size={16}
              />
              <Text style={menuStyles.itemText}>{isForking ? "Forking..." : "Fork to Chat"}</Text>
            </Pressable>

            {/* Dispatch-API only options */}
            {isDispatchApi && (
              <>
                <View style={menuStyles.divider} />
                <Pressable
                  style={menuStyles.item}
                  onPress={() => {
                    setMenuVisible(false);
                    InteractionManager.runAfterInteractions(handleRename);
                  }}
                >
                  <SymbolView
                    name={{ ios: "pencil", android: "edit", web: "edit" }}
                    tintColor="#fafafa"
                    size={16}
                  />
                  <Text style={menuStyles.itemText}>Rename</Text>
                </Pressable>
                <View style={menuStyles.divider} />
                <Pressable
                  style={menuStyles.item}
                  onPress={() => {
                    setMenuVisible(false);
                    InteractionManager.runAfterInteractions(handleDelete);
                  }}
                >
                  <SymbolView
                    name={{ ios: "trash", android: "delete", web: "delete" }}
                    tintColor="#ef4444"
                    size={16}
                  />
                  <Text style={[menuStyles.itemText, { color: "#ef4444" }]}>Delete</Text>
                </Pressable>
              </>
            )}
          </View>
        </Pressable>
      </Modal>
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
  menuButton: {
    paddingHorizontal: 4,
    paddingVertical: 4,
  },
});

const menuStyles = StyleSheet.create({
  overlay: {
    flex: 1,
  },
  dropdown: {
    position: "absolute",
    width: 180,
    backgroundColor: "#2a2a2e",
    borderRadius: 12,
    paddingVertical: 4,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 8,
  },
  item: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#3f3f46",
    marginHorizontal: 12,
  },
  itemText: {
    color: "#fafafa",
    fontSize: 16,
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
