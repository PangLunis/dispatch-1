import React, { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { useFocusEffect } from "@react-navigation/native";
import Swipeable from "react-native-gesture-handler/Swipeable";
import { impactMedium } from "@/src/utils/haptics";
import { useChatList, isCurrentlyUnread } from "@/src/hooks/useChatList";
import { ChatRow } from "@/src/components/ChatRow";
import { EmptyState } from "@/src/components/EmptyState";
import { branding } from "@/src/config/branding";
import { showDestructiveConfirm } from "@/src/utils/alert";
import type { Conversation } from "@/src/api/types";

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
      impactMedium();
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

  // Stable ref map for Swipeable instances — avoids creating refs on every render
  const swipeableRefs = useRef(new Map<string, Swipeable | null>()).current;

  const renderItem = useCallback(
    ({ item }: { item: Conversation }) => {
      const unread = isCurrentlyUnread(item);

      return (
        <Swipeable
          ref={(ref) => {
            if (ref) swipeableRefs.set(item.id, ref);
            else swipeableRefs.delete(item.id);
          }}
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
                    onPress={() => handleMarkUnread(item, swipeableRefs.get(item.id) ?? null)}
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
            isUnread={unread}
          />
        </Swipeable>
      );
    },
    [handleOpenChat, handleDeleteChat, handleMarkUnread, renderRightActions, swipeableRefs],
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
      <AnimatedFab onPress={handleNewChat} />
    </View>
  );
}

/** FAB with native-driver animated press scale */
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
