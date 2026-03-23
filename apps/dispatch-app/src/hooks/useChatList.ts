import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { getChats, createChat, deleteChat, markChatAsUnread as apiMarkChatAsUnread } from "../api/chats";
import type { Conversation } from "../api/types";
import { notifyUnreadChatCount } from "../state/unreadChats";

// ---------------------------------------------------------------------------
// Unified optimistic read/unread tracking (module-level, persists across navigations)
// ---------------------------------------------------------------------------

/** Optimistic override: 'read' = user opened it, 'unread' = user manually marked unread */
const _optimisticState = new Map<string, "read" | "unread">();

/** Map of chat ID -> last_message content when read (to detect new messages) */
const _readAtMessage = new Map<string, string | null>();

/** Mark a chat as read (call from chat detail screen) */
export function markChatAsRead(chatId: string): void {
  _optimisticState.set(chatId, "read");
}

/** Get the optimistic override for a chat */
export function getChatOptimisticState(
  chatId: string,
): "read" | "unread" | undefined {
  return _optimisticState.get(chatId);
}

// Legacy export — used by index.tsx for backward compat
export function isChatRead(chatId: string): boolean {
  return _optimisticState.get(chatId) === "read";
}

/** Update read tracking when new data arrives — clear overrides once reconciled */
function _updateReadTracking(conversations: Conversation[]): void {
  for (const conv of conversations) {
    const state = _optimisticState.get(conv.id);
    if (state === "read") {
      const prevMessage = _readAtMessage.get(conv.id);
      if (prevMessage === undefined) {
        // First time seeing this after marking read — record current last_message
        _readAtMessage.set(conv.id, conv.last_message);
      } else if (conv.last_message !== prevMessage) {
        // New message arrived since we read it — no longer "read"
        _optimisticState.delete(conv.id);
        _readAtMessage.delete(conv.id);
      }
    } else if (state === "unread") {
      // Clear optimistic unread once server confirms marked_unread = true
      if (conv.marked_unread) {
        _optimisticState.delete(conv.id);
      }
    }
  }
}

/** Check if a chat is unread based on server data (no optimistic overrides) */
function _isServerUnread(c: Conversation): boolean {
  if (c.marked_unread) return true;
  if (c.last_message_role !== "assistant" || !c.last_message_at) return false;
  if (c.last_opened_at) {
    return new Date(c.last_message_at) > new Date(c.last_opened_at);
  }
  return true; // No last_opened_at — assistant message is unread
}

interface UseChatListReturn {
  conversations: Conversation[];
  isLoading: boolean;
  error: string | null;
  loadConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<Conversation | null>;
  deleteConversation: (chatId: string) => Promise<boolean>;
  markAsUnread: (chatId: string) => Promise<void>;
}

export function useChatList(): UseChatListReturn {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const loadConversations = useCallback(async () => {
    try {
      const chats = await getChats();
      // Sort by last message time descending (most recent first)
      chats.sort((a, b) => {
        const timeA = a.last_message_at || a.created_at;
        const timeB = b.last_message_at || b.created_at;
        return timeB.localeCompare(timeA);
      });
      if (mountedRef.current) {
        _updateReadTracking(chats);
        // Count unread chats for tab badge
        const unreadCount = chats.filter((c) => {
          const opt = _optimisticState.get(c.id);
          if (opt === "read") return false;
          if (opt === "unread") return true;
          return _isServerUnread(c);
        }).length;
        notifyUnreadChatCount(unreadCount);
        setConversations(chats);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(
          err instanceof Error ? err.message : "Failed to load conversations",
        );
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  const createConversation = useCallback(
    async (title?: string): Promise<Conversation | null> => {
      try {
        const chat = await createChat(title);
        if (mountedRef.current) {
          setConversations((prev) => [chat, ...prev]);
        }
        return chat;
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to create conversation",
          );
        }
        return null;
      }
    },
    [],
  );

  const deleteConversation = useCallback(
    async (chatId: string): Promise<boolean> => {
      // Optimistically remove from list immediately
      let removed: Conversation[] = [];
      setConversations((prev) => {
        removed = prev.filter((c) => c.id === chatId);
        return prev.filter((c) => c.id !== chatId);
      });

      try {
        await deleteChat(chatId);
        return true;
      } catch (err) {
        if (mountedRef.current) {
          // Restore on failure
          setConversations((prev) => [...removed, ...prev]);
          setError(
            err instanceof Error
              ? err.message
              : "Failed to delete conversation",
          );
        }
        return false;
      }
    },
    [],
  );

  const markAsUnread = useCallback(
    async (chatId: string): Promise<void> => {
      // Optimistic: set module-level state + force re-render
      _optimisticState.set(chatId, "unread");
      _readAtMessage.delete(chatId);
      setConversations((prev) => [...prev]);

      try {
        await apiMarkChatAsUnread(chatId);
      } catch {
        // Rollback: clear optimistic state and re-fetch
        _optimisticState.delete(chatId);
        if (mountedRef.current) {
          await loadConversations();
        }
      }
    },
    [loadConversations],
  );

  // Initial load
  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // Poll for updates every 3 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      loadConversations();
    }, 3000);

    return () => clearInterval(interval);
  }, [loadConversations]);

  // Refresh on app foreground
  useEffect(() => {
    const handleAppStateChange = (nextState: AppStateStatus) => {
      if (nextState === "active") {
        loadConversations();
      }
    };

    const subscription = AppState.addEventListener(
      "change",
      handleAppStateChange,
    );

    return () => {
      subscription.remove();
    };
  }, [loadConversations]);

  // Cleanup
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return {
    conversations,
    isLoading,
    error,
    loadConversations,
    createConversation,
    deleteConversation,
    markAsUnread,
  };
}
