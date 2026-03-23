import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "@react-navigation/native";
import Swipeable from "react-native-gesture-handler/Swipeable";
import * as Haptics from "expo-haptics";
import { useChatList, getChatOptimisticState } from "@/src/hooks/useChatList";
import { ChatRow } from "@/src/components/ChatRow";
import { EmptyState } from "@/src/components/EmptyState";
import { branding } from "@/src/config/branding";
import { showDestructiveConfirm } from "@/src/utils/alert";
import type { Conversation } from "@/src/api/types";

/** Check if a chat is currently unread (server data + optimistic) */
function isCurrentlyUnread(conversation: Conversation): boolean {
  const opt = getChatOptimisticState(conversation.id);
  if (opt === "read") return false;
  if (opt === "unread") return true;
  if (conversation.marked_unread) return true;
  if (
    conversation.last_message_role === "assistant" &&
    conversation.last_message_at
  ) {
    if (conversation.last_opened_at) {
      return (
        new Date(conversation.last_message_at) >
        new Date(conversation.last_opened_at)
      );
    }
    return true;
  }
  return false;
}

export default function ChatListScreen() {
  const router = useRouter();
  const {
    conversations,
    isLoading,
    error,
    loadConversations,
    createConversation,
    deleteConversation,
    markAsUnread,
  } = useChatList();

  // Force re-render when screen gains focus (e.g., coming back from chat detail)
  // This ensures optimistic read state is reflected immediately
  const [, setFocusCount] = useState(0);
  useFocusEffect(
    useCallback(() => {
      setFocusCount((c) => c + 1);
      loadConversations();
    }, [loadConversations]),
  );

  // Track open swipeable refs to close them
  const openSwipeableRef = useRef<Swipeable | null>(null);
  // Suppress press events during/after swipe to prevent accidental navigation
  const swipeActiveRef = useRef(false);

  const handleNewChat = useCallback(async () => {
    const chat = await createConversation();
    if (chat) {
      router.push({ pathname: "/chat/[id]", params: { id: chat.id, chatTitle: chat.title } });
    }
  }, [createConversation, router]);

  const handleOpenChat = useCallback(
    (conversation: Conversation) => {
      // Don't navigate if a swipe just happened
      if (swipeActiveRef.current) {
        swipeActiveRef.current = false;
        return;
      }
      // Close any open swipeable
      openSwipeableRef.current?.close();
      router.push({
        pathname: "/chat/[id]",
        params: { id: conversation.id, chatTitle: conversation.title },
      });
    },
    [router],
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
      }
    },
    [deleteConversation],
  );

  const handleMarkUnread = useCallback(
    async (conversation: Conversation, swipeable: Swipeable | null) => {
      // Close swipeable first
      swipeable?.close();
      // Haptic feedback
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      // Optimistic update + API call
      await markAsUnread(conversation.id);
    },
    [markAsUnread],
  );

  const renderRightActions = useCallback(
    (conversation: Conversation) => {
      return (
        <Pressable
          onPress={() => handleDeleteChat(conversation)}
          style={styles.deleteAction}
          accessibilityLabel="Delete chat"
          accessibilityRole="button"
        >
          <Text style={styles.deleteActionText}>Delete</Text>
        </Pressable>
      );
    },
    [handleDeleteChat],
  );

  const renderItem = useCallback(
    ({ item }: { item: Conversation }) => {
      const optState = getChatOptimisticState(item.id);
      const unread = isCurrentlyUnread(item);
      const swipeableRef = React.createRef<Swipeable>();

      return (
        <Swipeable
          ref={swipeableRef}
          onSwipeableWillOpen={() => {
            swipeActiveRef.current = true;
          }}
          onSwipeableOpen={(direction, swipeable) => {
            openSwipeableRef.current = swipeable;
            // Full-swipe execution: mark unread when left actions revealed
            if (direction === "left") {
              handleMarkUnread(item, swipeable);
            }
          }}
          onSwipeableClose={() => {
            // Reset after a short delay to let press events pass
            setTimeout(() => {
              swipeActiveRef.current = false;
            }, 300);
          }}
          renderRightActions={() => renderRightActions(item)}
          {...(!unread
            ? {
                renderLeftActions: () => (
                  <Pressable
                    onPress={() => handleMarkUnread(item, swipeableRef.current)}
                    style={styles.unreadAction}
                    accessibilityLabel="Mark as unread"
                    accessibilityRole="button"
                  >
                    <Text style={styles.unreadActionText}>Unread</Text>
                  </Pressable>
                ),
              }
            : {})}
          overshootRight={false}
          overshootLeft={false}
          leftThreshold={40}
          friction={2}
        >
          <ChatRow
            conversation={item}
            onPress={() => handleOpenChat(item)}
            onLongPress={() => handleDeleteChat(item)}
            readOverride={optState}
          />
        </Swipeable>
      );
    },
    [handleOpenChat, handleDeleteChat, handleMarkUnread, renderRightActions],
  );

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={branding.accentColor} />
      </View>
    );
  }

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
        contentContainerStyle={
          conversations.length === 0 ? styles.emptyContainer : undefined
        }
        ListEmptyComponent={
          <EmptyState
            title="No conversations yet"
            subtitle="Tap + to start a new chat"
          />
        }
      />
      <Pressable
        onPress={handleNewChat}
        style={({ pressed }) => [
          styles.fab,
          { backgroundColor: branding.accentColor },
          pressed && styles.fabPressed,
        ]}
      >
        <Text style={styles.fabText}>+</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#09090b",
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#09090b",
  },
  emptyContainer: {
    flex: 1,
  },
  errorBanner: {
    backgroundColor: "#7f1d1d",
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  errorText: {
    color: "#fca5a5",
    fontSize: 14,
  },
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
  fabPressed: {
    opacity: 0.8,
  },
  fabText: {
    color: "#fff",
    fontSize: 28,
    fontWeight: "400",
    marginTop: -2,
  },
  deleteAction: {
    backgroundColor: "#ef4444",
    justifyContent: "center",
    alignItems: "center",
    width: 80,
  },
  deleteActionText: {
    color: "#ffffff",
    fontSize: 14,
    fontWeight: "600",
  },
  unreadAction: {
    backgroundColor: "#3478f6",
    justifyContent: "center",
    alignItems: "center",
    width: 80,
  },
  unreadActionText: {
    color: "#ffffff",
    fontSize: 14,
    fontWeight: "600",
  },
});
