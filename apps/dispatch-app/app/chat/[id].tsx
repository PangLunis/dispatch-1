import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, router } from "expo-router";
import { SymbolView } from "expo-symbols";
import {
  chatAdapter,
  useMessages,
  type DisplayMessage,
} from "@/src/hooks/useMessages";
import { MessageBubble } from "@/src/components/MessageBubble";
import { InputBar } from "@/src/components/InputBar";
import { ThinkingIndicator } from "@/src/components/ThinkingIndicator";
import { EmptyState } from "@/src/components/EmptyState";
import { useAudioPlayer } from "@/src/hooks/useAudioPlayer";
import { useSdkEvents } from "@/src/hooks/useSdkEvents";
import { updateChat, markChatAsOpened } from "@/src/api/chats";
import { createAgentSession, sendAgentMessage } from "@/src/api/agents";
import { screenStyles } from "@/src/styles/shared";
import { showPrompt, showAlert } from "@/src/utils/alert";
import { branding, sessionPrefix } from "@/src/config/branding";
import { markChatAsRead } from "@/src/hooks/useChatList";
import { setActiveChatId, dismissNotificationsForChat } from "@/src/hooks/usePushNotifications";

export default function ChatDetailScreen() {
  const { id, chatTitle } = useLocalSearchParams<{
    id: string;
    chatTitle?: string;
  }>();

  const [currentTitle, setCurrentTitle] = useState(chatTitle || id || "Chat");
  const adapter = useMemo(() => chatAdapter(id ?? ""), [id]);
  const { messages, isLoading, error, isThinking, sendMessage, sendMessageWithImage, retryMessage } =
    useMessages(adapter, id ? `chat:${id}` : undefined);

  const audioPlayer = useAudioPlayer();

  const [imageSendError, setImageSendError] = useState<string | null>(null);
  const [menuVisible, setMenuVisible] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ x: 0, y: 0 });
  const [isCreatingDebugSession, setIsCreatingDebugSession] = useState(false);
  const menuButtonRef = useRef<View>(null);

  // Optimistically mark as read, persist to server, and track active chat for push suppression
  useEffect(() => {
    if (id) {
      markChatAsRead(id);
      markChatAsOpened(id).catch(() => {}); // fire-and-forget server update
      setActiveChatId(id);
      dismissNotificationsForChat(id).catch(() => {});
    }
    return () => setActiveChatId(null);
  }, [id]);

  // Poll SDK events when thinking to show tool info
  // Use {sessionPrefix}:{chatId} format for the session_id so the server resolves the right session_name
  const sdkSessionId = useMemo(() => `${sessionPrefix}:${id ?? ""}`, [id]);

  // Find the last user message timestamp to scope SDK events to the current turn
  const lastUserMsgTs = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        return new Date(messages[i].timestamp).getTime();
      }
    }
    return undefined;
  }, [messages]);

  const { events: sdkEvents, isComplete: sdkComplete } = useSdkEvents(sdkSessionId, isThinking, lastUserMsgTs);

  // Hide thinking immediately when SDK events report turn complete
  const showThinking = isThinking && !sdkComplete;


  // Inverted FlatList: data is reversed so newest messages appear at the bottom.
  // FlatList with inverted=true renders from the bottom up, so we reverse the array.
  const invertedMessages = useMemo(
    () => [...messages].reverse(),
    [messages],
  );

  const handleSend = useCallback(
    (text: string) => {
      sendMessage(text);
    },
    [sendMessage],
  );

  const handleSendWithImage = useCallback(
    async (text: string, imageUri: string) => {
      setImageSendError(null);
      try {
        await sendMessageWithImage(text, imageUri, id ?? "voice");
      } catch (err) {
        setImageSendError(
          err instanceof Error ? err.message : "Failed to send image",
        );
      }
    },
    [id, sendMessageWithImage],
  );

  const handleRename = useCallback(async () => {
    const newTitle = await showPrompt("Rename Chat", "Enter a new title:", currentTitle);
    if (!newTitle || newTitle === currentTitle) return;
    try {
      await updateChat(id ?? "", newTitle);
      setCurrentTitle(newTitle);
    } catch (err) {
      showAlert("Error", err instanceof Error ? err.message : "Failed to rename chat");
    }
  }, [id, currentTitle]);

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
        style={localStyles.menuButton}
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

  const renderItem = useCallback(
    ({ item }: { item: DisplayMessage }) => (
      <MessageBubble message={item} audioState={audioPlayer} onRetry={retryMessage} />
    ),
    [audioPlayer, retryMessage],
  );

  const keyExtractor = useCallback((item: DisplayMessage) => item.id, []);


  return (
    <>
      <Stack.Screen
        options={{
          title: currentTitle,
          headerBackVisible: false,
          headerLeft: () => (
            <Pressable
              onPress={() => {
                if (router.canGoBack()) {
                  router.back();
                } else {
                  router.replace("/(tabs)");
                }
              }}
              hitSlop={8}
              style={{ flexDirection: "row", alignItems: "center", marginLeft: 0, paddingHorizontal: 4, gap: 4 }}
            >
              <SymbolView
                name={{ ios: "chevron.left", android: "arrow_back", web: "arrow_back" }}
                tintColor="#3b82f6"
                size={18}
                weight="semibold"
                style={{ width: 12, height: 20 }}
              />
              <Text style={{ color: "#3b82f6", fontSize: 17 }}>Chats</Text>
            </Pressable>
          ),
          headerStyle: { backgroundColor: "#09090b" },
          headerTintColor: "#fafafa",
          headerShadowVisible: false,
          headerRight,
        }}
      />
      <KeyboardAvoidingView
        style={screenStyles.container}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
      >

        {/* Show transient errors (image send failures, connection issues) */}
        {(imageSendError || (error && messages.length > 0)) ? (
          <View style={screenStyles.errorBanner}>
            <Text style={screenStyles.errorBannerText}>
              {imageSendError || error}
            </Text>
          </View>
        ) : null}

        {isLoading ? (
          <View style={screenStyles.loadingContainer}>
            <ActivityIndicator color="#71717a" size="small" />
          </View>
        ) : error && messages.length === 0 ? (
          <View style={screenStyles.errorContainer}>
            <Text style={screenStyles.errorText}>{error}</Text>
          </View>
        ) : messages.length === 0 ? (
          <EmptyState
            title="No messages yet"
            subtitle="Send a message to start the conversation"
          />
        ) : (
          <FlatList
            data={invertedMessages}
            inverted
            renderItem={renderItem}
            keyExtractor={keyExtractor}
            contentContainerStyle={screenStyles.messageList}
            showsVerticalScrollIndicator={false}
            keyboardDismissMode="interactive"
            keyboardShouldPersistTaps="handled"
          />
        )}
        {showThinking && <ThinkingIndicator events={sdkEvents} />}
        <InputBar
          onSend={handleSend}
          onSendWithImage={handleSendWithImage}
        />
      </KeyboardAvoidingView>

      {/* Dropdown menu */}
      <Modal
        visible={menuVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setMenuVisible(false)}
      >
        <Pressable
          style={localStyles.menuOverlay}
          onPress={() => setMenuVisible(false)}
        >
          <View
            style={[
              localStyles.menuDropdown,
              { top: menuPosition.y, left: menuPosition.x },
            ]}
          >
            <Pressable
              style={localStyles.menuItem}
              onPress={() => {
                setMenuVisible(false);
                // Delay to let the modal fully dismiss before showing Alert.prompt
                setTimeout(handleRename, 350);
              }}
            >
              <SymbolView
                name={{ ios: "pencil", android: "edit", web: "edit" }}
                tintColor="#fafafa"
                size={16}
              />
              <Text style={localStyles.menuItemText}>Rename</Text>
            </Pressable>
            <View style={localStyles.menuDivider} />
            <Pressable
              style={localStyles.menuItem}
              onPress={() => {
                setMenuVisible(false);
                router.push({
                  pathname: "/chat/notes",
                  params: { id, chatTitle: currentTitle },
                });
              }}
            >
              <SymbolView
                name={{ ios: "note.text", android: "description", web: "description" }}
                tintColor="#fafafa"
                size={16}
              />
              <Text style={localStyles.menuItemText}>Notes</Text>
            </Pressable>
            <View style={localStyles.menuDivider} />
            <Pressable
              style={[localStyles.menuItem, isCreatingDebugSession && { opacity: 0.5 }]}
              disabled={isCreatingDebugSession}
              onPress={() => {
                setMenuVisible(false);
                setTimeout(() => {
                  showPrompt(
                    "Debug Chat",
                    "Describe the issue you're seeing:",
                    async (context) => {
                      if (!context?.trim()) return;
                      setIsCreatingDebugSession(true);
                      try {
                        const session = await createAgentSession(`Debug: ${currentTitle}`);
                        const debugPrompt = [
                          "You are a debug agent investigating an issue in a dispatch-app chat session.",
                          "",
                          "## Target Chat",
                          `- Chat ID: ${id}`,
                          `- Chat Title: ${currentTitle}`,
                          `- Transcript path: ~/transcripts/dispatch-app/${id}/`,
                          `- Backend: dispatch-app`,
                          "",
                          "## User's Bug Report",
                          context.trim(),
                          "",
                          "## Investigation Steps",
                          "1. Read the chat transcript with: uv run ~/.claude/skills/sms-assistant/scripts/read_transcript.py --session dispatch-app/${id}",
                          `2. Check bus.db for recent events: sqlite3 ~/dispatch/state/bus.db "SELECT timestamp, event_type, tool_name, payload FROM sdk_events WHERE session_name LIKE '%${id}%' ORDER BY id DESC LIMIT 30"`,
                          "3. Check daemon logs if relevant: tail -100 ~/dispatch/state/daemon.log",
                          "4. Read relevant source code if the issue is in app behavior",
                          "",
                          "Diagnose the root cause and propose a specific fix.",
                        ].join("\n");
                        // Navigate immediately so user sees the session loading
                        router.push({
                          pathname: "/agents/[id]",
                          params: {
                            id: session.id,
                            sessionName: session.name,
                            sessionSource: "dispatch-api",
                            sessionType: "dispatch-api",
                          },
                        });
                        // Send debug prompt after navigation (fire-and-forget, session view will pick it up via polling)
                        sendAgentMessage(session.id, debugPrompt).catch((err) => {
                          showAlert("Error", "Debug session created but failed to send prompt. Try sending your message manually.");
                        });
                      } catch (err) {
                        showAlert("Error", "Failed to create debug session. Check your connection and try again.");
                      } finally {
                        setIsCreatingDebugSession(false);
                      }
                    },
                  );
                }, 350);
              }}
            >
              <SymbolView
                name={{ ios: "ant", android: "bug_report", web: "bug_report" }}
                tintColor="#fafafa"
                size={16}
              />
              <Text style={localStyles.menuItemText}>Debug Chat</Text>
            </Pressable>
          </View>
        </Pressable>
      </Modal>
    </>
  );
}

const localStyles = StyleSheet.create({
  menuButton: {
    paddingHorizontal: 4,
    paddingVertical: 4,
  },
  menuOverlay: {
    flex: 1,
  },
  menuDropdown: {
    position: "absolute",
    width: 160,
    backgroundColor: "#2a2a2e",
    borderRadius: 12,
    paddingVertical: 4,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 8,
  },
  menuItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  menuDivider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "#3f3f46",
    marginHorizontal: 12,
  },
  menuItemText: {
    color: "#fafafa",
    fontSize: 16,
  },
});
