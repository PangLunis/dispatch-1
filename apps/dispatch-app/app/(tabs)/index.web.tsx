/**
 * Web-specific chat list screen with responsive split view.
 *
 * Desktop (≥768px): side-by-side layout — chat list on left, chat detail on right.
 * Mobile (<768px): chat list only — tapping a chat navigates to /chat/[id] (same as native).
 *
 * Selected chat ID is stored in the URL hash (#chatId) so it persists across refresh.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "@react-navigation/native";
import { useChatList, isCurrentlyUnread } from "@/src/hooks/useChatList";
import { ChatRow } from "@/src/components/ChatRow";
import { ChatDetailPanel } from "@/src/components/ChatDetailPanel";
import { EmptyState } from "@/src/components/EmptyState";
import { branding } from "@/src/config/branding";
import { showDestructiveConfirm } from "@/src/utils/alert";
import { colors } from "@/src/config/colors";
import type { Conversation } from "@/src/api/types";

const DESKTOP_BREAKPOINT = 768;
const SIDEBAR_WIDTH = 360;

/** Read chat ID from URL hash */
function getHashChatId(): string | null {
  if (typeof window === "undefined") return null;
  const hash = window.location.hash.replace(/^#/, "");
  return hash || null;
}

/** Update URL hash without triggering navigation */
function setHashChatId(chatId: string | null) {
  if (typeof window === "undefined") return;
  if (chatId) {
    window.history.replaceState(null, "", `#${chatId}`);
  } else {
    window.history.replaceState(null, "", window.location.pathname);
  }
}

export default function ChatListWebScreen() {
  const { width } = useWindowDimensions();
  const isDesktop = width >= DESKTOP_BREAKPOINT;

  const router = useRouter();
  const {
    conversations,
    isLoading,
    error,
    loadConversations,
    createConversation,
    deleteConversation,
  } = useChatList();

  // Desktop split view state — initialize from URL hash
  const [selectedChatId, setSelectedChatId] = useState<string | null>(getHashChatId);
  const [selectedChatTitle, setSelectedChatTitle] = useState<string>("");

  // Resolve chat title from conversations list when loading from hash
  useEffect(() => {
    if (selectedChatId && !selectedChatTitle && conversations.length > 0) {
      const match = conversations.find((c) => c.id === selectedChatId);
      if (match) {
        setSelectedChatTitle(match.title);
      }
    }
  }, [selectedChatId, selectedChatTitle, conversations]);

  // Sync selected chat to URL hash
  useEffect(() => {
    if (isDesktop) {
      setHashChatId(selectedChatId);
    }
  }, [selectedChatId, isDesktop]);

  const [, setFocusCount] = useState(0);
  useFocusEffect(
    useCallback(() => {
      setFocusCount((c) => c + 1);
      loadConversations();
    }, [loadConversations]),
  );

  const selectChat = useCallback((id: string, title: string) => {
    setSelectedChatId(id);
    setSelectedChatTitle(title);
  }, []);

  const handleNewChat = useCallback(async () => {
    const chat = await createConversation();
    if (chat) {
      if (isDesktop) {
        selectChat(chat.id, chat.title);
      } else {
        router.push({ pathname: "/chat/[id]", params: { id: chat.id, chatTitle: chat.title } });
      }
    }
  }, [createConversation, router, isDesktop, selectChat]);

  const handleOpenChat = useCallback(
    (conversation: Conversation) => {
      if (isDesktop) {
        selectChat(conversation.id, conversation.title);
      } else {
        router.push({
          pathname: "/chat/[id]",
          params: { id: conversation.id, chatTitle: conversation.title },
        });
      }
    },
    [router, isDesktop, selectChat],
  );

  const handleDeleteChat = useCallback(
    async (conversation: Conversation) => {
      const confirmed = await showDestructiveConfirm(
        "Delete Chat",
        `Are you sure you want to delete "${conversation.title}"? This cannot be undone.`,
        "Delete",
      );
      if (confirmed) {
        deleteConversation(conversation.id);
        if (selectedChatId === conversation.id) {
          setSelectedChatId(null);
          setSelectedChatTitle("");
        }
      }
    },
    [deleteConversation, selectedChatId],
  );

  const handleDetailTitleChange = useCallback(
    (newTitle: string) => {
      setSelectedChatTitle(newTitle);
      loadConversations();
    },
    [loadConversations],
  );

  const handleDetailDelete = useCallback(() => {
    setSelectedChatId(null);
    setSelectedChatTitle("");
    loadConversations();
  }, [loadConversations]);

  const renderItem = useCallback(
    ({ item }: { item: Conversation }) => {
      const unread = isCurrentlyUnread(item);
      const isSelected = isDesktop && selectedChatId === item.id;

      return (
        <Pressable
          onPress={() => handleOpenChat(item)}
          onLongPress={() => handleDeleteChat(item)}
          style={isSelected ? styles.selectedRow : undefined}
        >
          <ChatRow
            conversation={item}
            onPress={() => handleOpenChat(item)}
            onLongPress={() => handleDeleteChat(item)}
            isUnread={unread}
          />
          {isSelected && <View style={styles.selectedIndicator} />}
        </Pressable>
      );
    },
    [handleOpenChat, handleDeleteChat, isDesktop, selectedChatId],
  );

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={branding.accentColor} />
      </View>
    );
  }

  // Mobile: same as native
  if (!isDesktop) {
    return (
      <View style={styles.container}>
        {error ? (
          <View style={styles.errorBanner}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}
        <FlatList
          data={conversations}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          refreshing={isLoading}
          onRefresh={loadConversations}
          contentContainerStyle={conversations.length === 0 ? styles.emptyContainer : undefined}
          ListEmptyComponent={
            <EmptyState title="No conversations yet" subtitle="Tap + to start a new chat" />
          }
        />
        <AnimatedFab onPress={handleNewChat} />
      </View>
    );
  }

  // Desktop: split view
  return (
    <View style={styles.splitContainer}>
      {/* Left panel: chat list */}
      <View style={[styles.sidebar, { width: SIDEBAR_WIDTH }]}>
        <View style={styles.sidebarHeader}>
          <Text style={styles.sidebarTitle}>Chats</Text>
          <Pressable onPress={handleNewChat} style={styles.newChatButton}>
            <Text style={styles.newChatButtonText}>+ New</Text>
          </Pressable>
        </View>
        {error ? (
          <View style={styles.errorBanner}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}
        <FlatList
          data={conversations}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          refreshing={isLoading}
          onRefresh={loadConversations}
          contentContainerStyle={conversations.length === 0 ? styles.emptyContainer : undefined}
          ListEmptyComponent={
            <EmptyState title="No conversations yet" subtitle='Click "+ New" to start a chat' />
          }
        />
      </View>

      {/* Divider */}
      <View style={styles.divider} />

      {/* Right panel: chat detail */}
      <View style={styles.detailPanel}>
        {selectedChatId ? (
          <ChatDetailPanel
            key={selectedChatId}
            chatId={selectedChatId}
            chatTitle={selectedChatTitle}
            onTitleChange={handleDetailTitleChange}
            onDelete={handleDetailDelete}
          />
        ) : (
          <View style={styles.noSelection}>
            <Text style={styles.noSelectionIcon}>💬</Text>
            <Text style={styles.noSelectionText}>Select a conversation</Text>
            <Text style={styles.noSelectionSubtext}>
              Choose a chat from the list or create a new one
            </Text>
          </View>
        )}
      </View>
    </View>
  );
}

function AnimatedFab({ onPress }: { onPress: () => void }) {
  const scale = useRef(new Animated.Value(1)).current;
  return (
    <Pressable
      onPress={onPress}
      onPressIn={() =>
        Animated.timing(scale, { toValue: 0.9, duration: 100, useNativeDriver: true }).start()
      }
      onPressOut={() =>
        Animated.timing(scale, { toValue: 1, duration: 150, useNativeDriver: true }).start()
      }
      accessibilityLabel="New chat"
      accessibilityRole="button"
    >
      <Animated.View
        style={[
          styles.fab,
          { backgroundColor: branding.accentColor, transform: [{ scale }] },
        ]}
      >
        <Text style={styles.fabText}>+</Text>
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
  },
  emptyContainer: {
    flex: 1,
  },
  errorBanner: {
    backgroundColor: colors.errorBg,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  errorText: {
    color: colors.errorLight,
    fontSize: 14,
  },

  // Split view
  splitContainer: {
    flex: 1,
    flexDirection: "row",
    backgroundColor: colors.background,
  },
  sidebar: {
    backgroundColor: colors.background,
  },
  sidebarHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  sidebarTitle: {
    color: colors.textPrimary,
    fontSize: 20,
    fontWeight: "700",
  },
  newChatButton: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 8,
    backgroundColor: branding.accentColor,
  },
  newChatButtonText: {
    color: colors.white,
    fontSize: 14,
    fontWeight: "600",
  },
  divider: {
    width: 1,
    backgroundColor: colors.border,
  },
  detailPanel: {
    flex: 1,
  },

  // Selected chat row highlight
  selectedRow: {
    backgroundColor: "#1e293b",
    position: "relative",
  },
  selectedIndicator: {
    position: "absolute",
    left: 0,
    top: 4,
    bottom: 4,
    width: 3,
    borderRadius: 2,
    backgroundColor: branding.accentColor,
  },

  // No selection placeholder
  noSelection: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
  },
  noSelectionIcon: {
    fontSize: 48,
    marginBottom: 16,
    opacity: 0.4,
  },
  noSelectionText: {
    color: colors.textSecondary,
    fontSize: 18,
    fontWeight: "600",
    marginBottom: 8,
  },
  noSelectionSubtext: {
    color: colors.textMuted,
    fontSize: 14,
  },

  // FAB (mobile only)
  fab: {
    position: "absolute",
    right: 20,
    bottom: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 6,
  },
  fabText: {
    color: "#fff",
    fontSize: 28,
    fontWeight: "400",
    marginTop: -2,
  },
});
