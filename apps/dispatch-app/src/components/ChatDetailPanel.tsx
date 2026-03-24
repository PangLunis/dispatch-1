/**
 * Embeddable chat detail panel — used by the web split view.
 * This is a headless version of chat/[id].tsx without Stack.Screen navigation.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { updateChat, markChatAsOpened, deleteChat } from "@/src/api/chats";
import { screenStyles } from "@/src/styles/shared";
import { showPrompt, showAlert, showDestructiveConfirm } from "@/src/utils/alert";
import { branding, sessionPrefix } from "@/src/config/branding";
import { markChatAsRead } from "@/src/hooks/useChatList";
import { setActiveChatId, dismissNotificationsForChat } from "@/src/hooks/usePushNotifications";
import { colors } from "@/src/config/colors";

interface ChatDetailPanelProps {
  chatId: string;
  chatTitle: string;
  onTitleChange?: (newTitle: string) => void;
  onDelete?: () => void;
}

export function ChatDetailPanel({ chatId, chatTitle, onTitleChange, onDelete }: ChatDetailPanelProps) {
  const [currentTitle, setCurrentTitle] = useState(chatTitle);
  const adapter = useMemo(() => chatAdapter(chatId), [chatId]);
  const { messages, isLoading, error, isThinking, sendMessage, sendMessageWithImage, retryMessage } =
    useMessages(adapter, `chat:${chatId}`);

  const audioPlayer = useAudioPlayer();
  const [imageSendError, setImageSendError] = useState<string | null>(null);

  // Sync title prop changes
  useEffect(() => {
    setCurrentTitle(chatTitle);
  }, [chatTitle]);

  // Mark as read and track active chat
  useEffect(() => {
    if (chatId) {
      markChatAsRead(chatId);
      markChatAsOpened(chatId).catch(() => {});
      setActiveChatId(chatId);
      dismissNotificationsForChat(chatId).catch(() => {});
    }
    return () => setActiveChatId(null);
  }, [chatId]);

  // Poll SDK events when thinking
  const sdkSessionId = useMemo(() => `${sessionPrefix}:${chatId}`, [chatId]);
  const { events: sdkEvents, isComplete: sdkComplete } = useSdkEvents(sdkSessionId, isThinking);
  const showThinking = isThinking && !sdkComplete;

  const invertedMessages = useMemo(() => [...messages].reverse(), [messages]);

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
        await sendMessageWithImage(text, imageUri, chatId);
      } catch (err) {
        setImageSendError(err instanceof Error ? err.message : "Failed to send image");
      }
    },
    [chatId, sendMessageWithImage],
  );

  const handleRename = useCallback(async () => {
    const newTitle = await showPrompt("Rename Chat", "Enter a new title:", currentTitle);
    if (!newTitle || newTitle === currentTitle) return;
    try {
      await updateChat(chatId, newTitle);
      setCurrentTitle(newTitle);
      onTitleChange?.(newTitle);
    } catch (err) {
      showAlert("Error", err instanceof Error ? err.message : "Failed to rename chat");
    }
  }, [chatId, currentTitle, onTitleChange]);

  const handleDelete = useCallback(async () => {
    const confirmed = await showDestructiveConfirm(
      "Delete Chat",
      `Delete "${currentTitle}" and all its messages? This can't be undone.`,
    );
    if (!confirmed) return;
    try {
      await deleteChat(chatId);
      onDelete?.();
    } catch (err) {
      showAlert("Error", err instanceof Error ? err.message : "Failed to delete chat");
    }
  }, [chatId, currentTitle, onDelete]);

  const renderItem = useCallback(
    ({ item }: { item: DisplayMessage }) => (
      <MessageBubble message={item} audioState={audioPlayer} onRetry={retryMessage} />
    ),
    [audioPlayer, retryMessage],
  );

  const keyExtractor = useCallback((item: DisplayMessage) => item.id, []);

  return (
    <View style={styles.container}>
      {/* Inline header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {currentTitle}
        </Text>
        <View style={styles.headerActions}>
          <Pressable onPress={handleRename} style={styles.headerButton}>
            <SymbolView
              name={{ ios: "pencil", android: "edit", web: "edit" }}
              tintColor={branding.accentColor}
              size={16}
            />
            <Text style={styles.headerButtonText}>Rename</Text>
          </Pressable>
          <Pressable onPress={handleDelete} style={styles.headerButton}>
            <SymbolView
              name={{ ios: "trash", android: "delete", web: "delete" }}
              tintColor={colors.error}
              size={16}
            />
          </Pressable>
        </View>
      </View>

      {/* Chat content */}
      <View style={styles.chatArea}>
        {(imageSendError || (error && messages.length > 0)) ? (
          <View style={screenStyles.errorBanner}>
            <Text style={screenStyles.errorBannerText}>{imageSendError || error}</Text>
          </View>
        ) : null}

        {isLoading ? (
          <View style={screenStyles.loadingContainer}>
            <ActivityIndicator color={colors.textMuted} size="small" />
          </View>
        ) : error && messages.length === 0 ? (
          <View style={screenStyles.errorContainer}>
            <Text style={screenStyles.errorText}>{error}</Text>
          </View>
        ) : messages.length === 0 ? (
          <EmptyState title="No messages yet" subtitle="Send a message to start the conversation" />
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
        <ThinkingIndicator events={sdkEvents} visible={showThinking} />
        <InputBar
          onSend={handleSend}
          onSendWithImage={handleSendWithImage}
          chatId={`${sessionPrefix}:${chatId}`}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    backgroundColor: colors.background,
  },
  headerTitle: {
    color: colors.textPrimary,
    fontSize: 18,
    fontWeight: "600",
    flex: 1,
    marginRight: 12,
  },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  headerButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  headerButtonText: {
    color: branding.accentColor,
    fontSize: 14,
    fontWeight: "500",
  },
  chatArea: {
    flex: 1,
  },
});
