import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useFocusEffect } from "@react-navigation/native";
import { SymbolView } from "expo-symbols";
import Swipeable from "react-native-gesture-handler/Swipeable";
import { impactMedium } from "@/src/utils/haptics";
import { useChatList, isCurrentlyUnread } from "@/src/hooks/useChatList";
import { ChatRow } from "@/src/components/ChatRow";
import { EmptyState } from "@/src/components/EmptyState";
import { branding } from "@/src/config/branding";
import { showDestructiveConfirm } from "@/src/utils/alert";
import { searchChats } from "@/src/api/chats";
import type { Conversation, SearchResult } from "@/src/api/types";

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

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isSearchActive = searchQuery.length > 0;

  // Debounced search
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);

    if (!searchQuery.trim()) {
      setSearchResults([]);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    searchDebounceRef.current = setTimeout(async () => {
      try {
        const res = await searchChats(searchQuery.trim());
        setSearchResults(res.results);
      } catch {
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 300);

    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
  }, [searchQuery]);

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

  // Group search results by chat for display
  const groupedResults = React.useMemo(() => {
    const groups = new Map<string, { chatId: string; chatTitle: string; results: SearchResult[] }>();
    for (const r of searchResults) {
      let group = groups.get(r.chat_id);
      if (!group) {
        group = { chatId: r.chat_id, chatTitle: r.chat_title, results: [] };
        groups.set(r.chat_id, group);
      }
      group.results.push(r);
    }
    return Array.from(groups.values());
  }, [searchResults]);

  // Parse FTS5 snippet markers (<<match>>) into bold Text elements
  const renderHighlightedSnippet = useCallback((snippet: string) => {
    const parts = snippet.split(/(<<.*?>>)/g);
    return parts.map((part, i) => {
      if (part.startsWith("<<") && part.endsWith(">>")) {
        return (
          <Text key={i} style={styles.searchResultHighlight}>
            {part.slice(2, -2)}
          </Text>
        );
      }
      return part;
    });
  }, []);

  const renderSearchResult = useCallback(
    ({ item }: { item: { chatId: string; chatTitle: string; results: SearchResult[] } }) => (
      <Pressable
        onPress={() => router.push({
          pathname: "/chat/[id]",
          params: { id: item.chatId, chatTitle: item.chatTitle },
        })}
        style={({ pressed }) => [styles.searchGroup, pressed && styles.searchGroupPressed]}
      >
        <Text style={styles.searchGroupTitle} numberOfLines={1}>{item.chatTitle}</Text>
        {item.results.slice(0, 3).map((r) => (
          <View key={r.message_id} style={styles.searchResultRow}>
            <Text style={styles.searchResultRole}>{r.role === "user" ? "You" : "Sven"}</Text>
            <Text style={styles.searchResultSnippet} numberOfLines={2}>
              {renderHighlightedSnippet(r.snippet)}
            </Text>
          </View>
        ))}
        {item.results.length > 3 && (
          <Text style={styles.searchMoreText}>+{item.results.length - 3} more matches</Text>
        )}
      </Pressable>
    ),
    [router],
  );

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={branding.accentColor} />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      {/* Search bar replacing header */}
      <View style={styles.searchBarContainer}>
        <View style={styles.searchBar}>
          <SymbolView
            name={{ ios: "magnifyingglass", android: "search", web: "search" }}
            tintColor="#71717a"
            size={16}
            style={styles.searchIcon}
          />
          <TextInput
            style={styles.searchInput}
            placeholder="Search messages..."
            placeholderTextColor="#52525b"
            value={searchQuery}
            onChangeText={setSearchQuery}
            autoCorrect={false}
            autoCapitalize="none"
            returnKeyType="search"
          />
          {searchQuery.length > 0 && (
            <Pressable onPress={() => setSearchQuery("")} hitSlop={8}>
              <SymbolView
                name={{ ios: "xmark.circle.fill", android: "cancel", web: "cancel" }}
                tintColor="#71717a"
                size={16}
              />
            </Pressable>
          )}
        </View>
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {isSearchActive ? (
        // Search results view
        isSearching ? (
          <View style={styles.searchLoadingContainer}>
            <ActivityIndicator color="#71717a" size="small" />
          </View>
        ) : searchResults.length === 0 ? (
          <EmptyState
            title="No results"
            subtitle={`No messages matching "${searchQuery}"`}
          />
        ) : (
          <FlatList
            data={groupedResults}
            keyExtractor={(item) => item.chatId}
            renderItem={renderSearchResult}
            contentContainerStyle={styles.searchResultsList}
            keyboardDismissMode="on-drag"
            keyboardShouldPersistTaps="handled"
          />
        )
      ) : (
        // Normal chat list
        <>
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
            keyboardDismissMode="on-drag"
            keyboardShouldPersistTaps="handled"
          />
          <AnimatedFab onPress={handleNewChat} />
        </>
      )}
    </SafeAreaView>
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
  searchBarContainer: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 8,
    backgroundColor: "#09090b",
  },
  searchBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#1c1c1e",
    borderRadius: 10,
    paddingHorizontal: 10,
    height: 36,
  },
  searchIcon: {
    width: 16,
    height: 16,
    marginRight: 6,
  },
  searchInput: {
    flex: 1,
    color: "#fafafa",
    fontSize: 16,
    paddingVertical: 0,
  },
  searchLoadingContainer: {
    flex: 1,
    alignItems: "center",
    paddingTop: 40,
  },
  searchResultsList: {
    paddingHorizontal: 0,
  },
  searchGroup: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#27272a",
  },
  searchGroupPressed: {
    backgroundColor: "#18181b",
  },
  searchGroupTitle: {
    color: "#fafafa",
    fontSize: 16,
    fontWeight: "600",
    marginBottom: 6,
  },
  searchResultRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    marginTop: 4,
  },
  searchResultRole: {
    color: "#71717a",
    fontSize: 13,
    fontWeight: "600",
    width: 36,
    marginTop: 1,
  },
  searchResultSnippet: {
    color: "#a1a1aa",
    fontSize: 14,
    flex: 1,
    lineHeight: 20,
  },
  searchResultHighlight: {
    color: "#fafafa",
    fontWeight: "700",
  },
  searchMoreText: {
    color: "#52525b",
    fontSize: 13,
    marginTop: 6,
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
