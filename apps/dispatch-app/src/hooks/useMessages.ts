import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { getMessages, sendPrompt, sendPromptWithImage } from "../api/chats";
import { getAgentMessages, sendAgentMessage } from "../api/agents";
import type { ChatMessage, AgentMessage } from "../api/types";
import { MESSAGE_POLL_INTERVAL } from "../config/constants";
import { generateUUID } from "../utils/uuid";

// ---------------------------------------------------------------------------
// Unified message type used by the UI layer
// ---------------------------------------------------------------------------

export interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string; // ISO string
  isPending?: boolean;
  sendFailed?: boolean; // true when send failed — shows "Not Delivered" + retry
  serverMessageId?: string; // idempotency key sent to server — reused on retry to prevent duplicates
  audioUrl?: string | null;
  imageUrl?: string | null;
  localImageUri?: string | null; // optimistic preview (local file URI)
}

// ---------------------------------------------------------------------------
// Adapter interface — lets useMessages work with chats OR agents
// ---------------------------------------------------------------------------

export interface FetchResult {
  messages: DisplayMessage[];
  is_thinking?: boolean;
}

export interface MessageAdapter {
  /** Fetch messages, optionally only those after `sinceTs` (ISO string) */
  fetchMessages(opts: {
    sinceTs?: string;
  }): Promise<FetchResult>;

  /** Send a new message, returns a temporary id. messageId is an idempotency key for dedup. */
  sendMessage(text: string, messageId?: string): Promise<{ id: string }>;

  /** Polling interval in ms */
  pollInterval: number;
}

// ---------------------------------------------------------------------------
// Chat adapter — wraps src/api/chats.ts
// ---------------------------------------------------------------------------

export function chatAdapter(chatId: string): MessageAdapter {
  return {
    pollInterval: MESSAGE_POLL_INTERVAL,

    async fetchMessages({ sinceTs }) {
      const res = await getMessages(chatId, sinceTs);
      return {
        messages: (res.messages ?? []).map(chatMessageToDisplay),
        is_thinking: res.is_thinking,
      };
    },

    async sendMessage(text: string, messageId?: string) {
      const res = await sendPrompt(text, chatId, messageId);
      return { id: res.request_id };
    },
  };
}

function chatMessageToDisplay(m: ChatMessage): DisplayMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    timestamp: m.created_at,
    audioUrl: m.audio_url,
    imageUrl: m.image_url,
  };
}

// ---------------------------------------------------------------------------
// Agent adapter — wraps src/api/agents.ts
// ---------------------------------------------------------------------------

export function agentAdapter(sessionId: string): MessageAdapter {
  return {
    pollInterval: 2000,

    async fetchMessages({ sinceTs }) {
      const opts: { after_ts?: number } = {};
      if (sinceTs) {
        opts.after_ts = new Date(sinceTs).getTime();
      }
      const res = await getAgentMessages(sessionId, opts);
      return {
        messages: (res.messages ?? []).map(agentMessageToDisplay),
        is_thinking: res.is_thinking,
      };
    },

    async sendMessage(text: string, messageId?: string) {
      const res = await sendAgentMessage(sessionId, text, messageId);
      return { id: res.message_id ?? generateUUID() };
    },
  };
}

function agentMessageToDisplay(m: AgentMessage): DisplayMessage {
  return {
    id: m.id,
    role: m.role === "user" ? "user" : "assistant",
    content: m.text,
    timestamp: new Date(m.timestamp_ms).toISOString(),
  };
}

// ---------------------------------------------------------------------------
// In-memory message cache — prevents flash when re-entering a chat
// ---------------------------------------------------------------------------

const messageCache = new Map<string, { messages: DisplayMessage[]; isThinking: boolean }>();

// ---------------------------------------------------------------------------
// useMessages hook
// ---------------------------------------------------------------------------

export interface UseMessagesReturn {
  messages: DisplayMessage[];
  isLoading: boolean;
  error: string | null;
  isThinking: boolean;
  sendMessage: (text: string) => Promise<void>;
  sendMessageWithImage: (text: string, imageUri: string, chatId: string) => Promise<void>;
  retryMessage: (messageId: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useMessages(adapter: MessageAdapter, cacheKey?: string): UseMessagesReturn {
  // Don't use cached messages on mount — always start fresh to avoid flashing stale data.
  // The cache is still written to (below) for potential future use, but on mount we
  // always do a clean load to ensure the user sees current data.
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);

  // Write-through cache so re-entering chat shows latest data instantly
  const cacheKeyRef = useRef(cacheKey);
  cacheKeyRef.current = cacheKey;
  useEffect(() => {
    if (cacheKeyRef.current) {
      messageCache.set(cacheKeyRef.current, { messages, isThinking });
    }
  }, [messages, isThinking]);

  const mountedRef = useRef(true);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const adapterRef = useRef(adapter);
  adapterRef.current = adapter;

  // Track the latest timestamp we've seen for incremental polling
  const latestTsRef = useRef<string | undefined>(undefined);

  // Track consecutive poll failures to surface persistent connection issues
  const pollFailCountRef = useRef(0);
  const MAX_SILENT_POLL_FAILURES = 5;


  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  const updateLatestTs = useCallback((msgs: DisplayMessage[]) => {
    if (msgs.length === 0) return;
    const newest = msgs.reduce((a, b) =>
      a.timestamp > b.timestamp ? a : b,
    );
    if (
      !latestTsRef.current ||
      newest.timestamp > latestTsRef.current
    ) {
      latestTsRef.current = newest.timestamp;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Initial load
  // -----------------------------------------------------------------------

  const loadInitial = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await adapterRef.current.fetchMessages({});
      if (!mountedRef.current) return;
      setMessages(result.messages);
      updateLatestTs(result.messages);

      // Use server-reported thinking status if available, otherwise infer from last message role
      if (result.is_thinking !== undefined) {
        setIsThinking(result.is_thinking);
      } else if (result.messages.length > 0 && result.messages[result.messages.length - 1].role === "user") {
        setIsThinking(true);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err.message : "Failed to load messages");
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, [updateLatestTs]);

  // -----------------------------------------------------------------------
  // Poll for new messages
  // -----------------------------------------------------------------------

  const poll = useCallback(async () => {
    try {
      const sinceTs = latestTsRef.current;
      const result = await adapterRef.current.fetchMessages({
        sinceTs,
      });
      if (!mountedRef.current) return;

      // Reset failure count and clear connection error on success
      if (pollFailCountRef.current >= MAX_SILENT_POLL_FAILURES) {
        setError(null);
      }
      pollFailCountRef.current = 0;

      const newMsgs = result.messages;

      // Update thinking status from server — no optimistic override
      if (result.is_thinking !== undefined) {
        setIsThinking(result.is_thinking);
      }

      if (newMsgs.length === 0) return;

      setMessages((prev) => {
        // Merge: remove pending duplicates, add new, dedup by id
        const existingIds = new Set(prev.map((m) => m.id));
        const truly_new = newMsgs.filter((m) => !existingIds.has(m.id));

        if (truly_new.length === 0) return prev;

        // Remove pending messages whose content matches an incoming message
        const newContents = new Set(truly_new.map((m) => m.content));
        const filtered = prev.filter(
          (m) => !m.isPending || !newContents.has(m.content),
        );

        return [...filtered, ...truly_new];
      });

      updateLatestTs(newMsgs);

      // Fallback: check if assistant has responded — stop thinking indicator
      // (only used when server doesn't provide is_thinking)
      if (result.is_thinking === undefined) {
        const hasAssistantReply = newMsgs.some((m) => m.role === "assistant");
        if (hasAssistantReply) {
          setIsThinking(false);
        }
      }
    } catch (err) {
      // Surface persistent connection issues after repeated failures
      pollFailCountRef.current += 1;
      if (
        mountedRef.current &&
        pollFailCountRef.current >= MAX_SILENT_POLL_FAILURES
      ) {
        setError("Connection lost — retrying...");
      }
    }
  }, [updateLatestTs]);

  // -----------------------------------------------------------------------
  // Start / stop polling
  // -----------------------------------------------------------------------

  const startPolling = useCallback(() => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(poll, adapterRef.current.pollInterval);
  }, [poll]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Send message — optimistic insert
  // -----------------------------------------------------------------------

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      const serverMessageId = generateUUID();
      const pendingId = `pending-${Date.now()}-${Math.random()}`;
      const pendingMsg: DisplayMessage = {
        id: pendingId,
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
        isPending: true,
        serverMessageId,
      };

      setMessages((prev) => [...prev, pendingMsg]);
      // Don't set isThinking optimistically — let the server drive it
      setError(null);

      try {
        await adapterRef.current.sendMessage(trimmed, serverMessageId);
      } catch (err) {
        if (!mountedRef.current) return;
        // Mark message as failed instead of removing — user can retry
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingId
              ? { ...m, isPending: false, sendFailed: true }
              : m,
          ),
        );
        setIsThinking(false);
      }
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Retry a failed message
  // -----------------------------------------------------------------------

  const retryMessage = useCallback(
    async (messageId: string) => {
      const failedMsg = messages.find((m) => m.id === messageId && m.sendFailed);
      if (!failedMsg) return;

      // Mark as pending again
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? { ...m, isPending: true, sendFailed: false }
            : m,
        ),
      );
      // Don't set isThinking optimistically — let the server drive it

      try {
        await adapterRef.current.sendMessage(failedMsg.content, failedMsg.serverMessageId);
      } catch (err) {
        if (!mountedRef.current) return;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? { ...m, isPending: false, sendFailed: true }
              : m,
          ),
        );
        setIsThinking(false);
      }
    },
    [messages],
  );

  // -----------------------------------------------------------------------
  // Send message with image — optimistic insert with local preview
  // -----------------------------------------------------------------------

  const sendMessageWithImage = useCallback(
    async (text: string, imageUri: string, chatId: string) => {
      const trimmed = text.trim();

      const pendingId = `pending-img-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const pendingMsg: DisplayMessage = {
        id: pendingId,
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
        isPending: true,
        localImageUri: imageUri,
      };

      setMessages((prev) => [...prev, pendingMsg]);
      // Don't set isThinking optimistically — let the server drive it
      setError(null);

      try {
        await sendPromptWithImage(trimmed, imageUri, chatId);
      } catch (err) {
        if (!mountedRef.current) return;
        setMessages((prev) => prev.filter((m) => m.id !== pendingId));
        setIsThinking(false);
        setError(
          err instanceof Error ? err.message : "Failed to send image",
        );
      }
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Refresh (pull to refresh or manual)
  // -----------------------------------------------------------------------

  const refresh = useCallback(async () => {
    latestTsRef.current = undefined;
    await loadInitial();
  }, [loadInitial]);

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  useEffect(() => {
    mountedRef.current = true;

    loadInitial().then(() => {
      if (mountedRef.current) startPolling();
    });

    return () => {
      mountedRef.current = false;
      stopPolling();
      // Clear cache on unmount so stale data doesn't flash on re-entry
      if (cacheKeyRef.current) {
        messageCache.delete(cacheKeyRef.current);
      }
    };
  }, [loadInitial, startPolling, stopPolling]);

  // Pause polling when app backgrounds, resume when foregrounded
  useEffect(() => {
    const handleAppState = (nextState: AppStateStatus) => {
      if (nextState === "active") {
        // Full reload on foreground to avoid stale data
        loadInitial().then(() => {
          if (mountedRef.current) startPolling();
        });
      } else {
        stopPolling();
      }
    };
    const sub = AppState.addEventListener("change", handleAppState);
    return () => sub.remove();
  }, [poll, startPolling, stopPolling]);

  return {
    messages,
    isLoading,
    error,
    isThinking,
    sendMessage,
    sendMessageWithImage,
    retryMessage,
    refresh,
  };
}
