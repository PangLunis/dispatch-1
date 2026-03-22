import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { getChats, createChat, deleteChat } from "../api/chats";
import type { Conversation } from "../api/types";
import { notifyUnreadChatCount } from "../state/unreadChats";

// ---------------------------------------------------------------------------
// Optimistic read tracking (module-level, persists across screen navigations)
// ---------------------------------------------------------------------------

/** Set of chat IDs the user has opened (treated as "read") */
const _readChatIds = new Set<string>();

/** Map of chat ID -> last_message content when read (to detect new messages) */
const _readAtMessage = new Map<string, string | null>();

/** Mark a chat as read (call from chat detail screen) */
export function markChatAsRead(chatId: string): void {
  _readChatIds.add(chatId);
}

/** Check if a chat should be treated as read (optimistic) */
export function isChatRead(chatId: string): boolean {
  return _readChatIds.has(chatId);
}

/** Update read tracking when new data arrives — clear read if a new message arrived */
function _updateReadTracking(conversations: Conversation[]): void {
  for (const conv of conversations) {
    if (_readChatIds.has(conv.id)) {
      const prevMessage = _readAtMessage.get(conv.id);
      if (prevMessage === undefined) {
        // First time seeing this after marking read — record current last_message
        _readAtMessage.set(conv.id, conv.last_message);
      } else if (conv.last_message !== prevMessage) {
        // New message arrived since we read it — no longer "read"
        _readChatIds.delete(conv.id);
        _readAtMessage.delete(conv.id);
      }
    }
  }
}

interface UseChatListReturn {
  conversations: Conversation[];
  isLoading: boolean;
  error: string | null;
  loadConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<Conversation | null>;
  deleteConversation: (chatId: string) => Promise<boolean>;
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
          if (_readChatIds.has(c.id)) return false;
          if (c.last_message_role !== "assistant" || !c.last_message_at) return false;
          if (c.last_opened_at) {
            return new Date(c.last_message_at) > new Date(c.last_opened_at);
          }
          return true; // No last_opened_at — assistant message is unread
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
  };
}
