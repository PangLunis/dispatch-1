import { useCallback, useEffect, useRef, useState } from "react";
import { ActionSheetIOS, Platform } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { getApiBaseUrl } from "../config/constants";
import { getDeviceToken, apiRequest } from "../api/client";
import { impactLight, impactMedium, notificationError } from "../utils/haptics";
import { branding } from "../config/branding";
import { useSpeechCapture } from "./useSpeechCapture";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type VoiceState = "IDLE" | "LISTENING" | "WAITING" | "ERROR";

export interface TranscriptEntry {
  role: "user" | "assistant";
  text: string;
  key: string;
}

interface ChatOption {
  id: string;
  title: string;
}

interface SSEThinking { type: "thinking" }
interface SSEAgentText { type: "agent_text"; text: string; message_id: string }
interface SSEAudioReady { type: "audio_ready"; audio_url: string }
interface SSEError { type: "error"; message: string }
interface SSETimeout { type: "timeout"; message: string }
type SSEEvent = SSEThinking | SSEAgentText | SSEAudioReady | SSEError | SSETimeout;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MIN_TRANSCRIPT_LENGTH = 3;
const SUBMIT_DEBOUNCE_MS = 500;
const AUTO_RELISTEN_DELAY_MS = 1500; // Pause before auto-restarting after agent response
export const NEW_CHAT_ID = "__new__";

// Unique key generator for transcript entries (module-scoped is fine for non-HMR;
// survives across component re-mounts within the same JS context)
let entryCounter = 0;
function nextEntryKey(): string {
  return `e-${Date.now()}-${++entryCounter}`;
}

/** Parse a single SSE line into an event object, or null if unparseable. */
function parseSSELine(line: string): SSEEvent | null {
  if (!line.startsWith("data: ")) return null;
  const jsonStr = line.slice(6).trim();
  if (!jsonStr || jsonStr === "[DONE]") return null;
  try {
    return JSON.parse(jsonStr) as SSEEvent;
  } catch (err) {
    console.warn("[VoiceAgent] Malformed SSE JSON:", jsonStr, err);
    return null;
  }
}

// ---------------------------------------------------------------------------
// State display config
// ---------------------------------------------------------------------------

export const STATE_LABELS: Record<VoiceState, string> = {
  IDLE: "Tap to start",
  LISTENING: "Listening...",
  WAITING: "Thinking...",
  ERROR: "Error",
};

export const STATE_COLORS: Record<VoiceState, string> = {
  IDLE: "#71717a",
  LISTENING: "#22c55e", // Green — distinct from error red
  WAITING: branding.accentColor,
  ERROR: "#ef4444",
};

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export type ErrorSource = "stt" | "agent";

export interface VoiceAgentReturn {
  // State
  voiceState: VoiceState;
  entries: TranscriptEntry[];
  currentAgentText: string | null;
  errorMessage: string | null;
  errorSource: ErrorSource | null;

  // STT live preview
  sttPartial: string;
  sttTranscript: string;

  // Chat picker
  chatOptions: ChatOption[];
  selectedChatId: string;
  selectedLabel: string;
  showChatPicker: () => void;

  // Actions
  startListening: () => Promise<void>;
  sendNow: () => void;
  stopAll: () => void;
  retryFromError: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useVoiceAgent(): VoiceAgentReturn {
  const stt = useSpeechCapture({ contextualStrings: [branding.displayName] });

  const [voiceState, setVoiceState] = useState<VoiceState>("IDLE");
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<ErrorSource | null>(null);
  const [currentAgentText, setCurrentAgentText] = useState<string | null>(null);
  const lastUserTextRef = useRef<string>("");

  // Chat picker
  const [chatOptions, setChatOptions] = useState<ChatOption[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<string>(NEW_CHAT_ID);

  const sseAbortRef = useRef<AbortController | null>(null);
  const lastSubmitTimeRef = useRef(0);
  const voiceStateRef = useRef<VoiceState>("IDLE");
  const activeChatIdRef = useRef<string>(NEW_CHAT_ID);
  const relistenTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep refs in sync
  useEffect(() => { voiceStateRef.current = voiceState; }, [voiceState]);
  useEffect(() => { activeChatIdRef.current = selectedChatId; }, [selectedChatId]);

  // Fetch chats on mount
  useEffect(() => {
    (async () => {
      try {
        const data = await apiRequest<{ chats: Array<{ id: string; title: string }> }>("/chats");
        setChatOptions(data.chats.map((c) => ({
          id: c.id,
          title: c.title || c.id.slice(0, 8),
        })));
      } catch (err) {
        console.warn("[VoiceAgent] Failed to fetch chats:", err);
      }
    })();
  }, []);

  // Create a new chat
  const createNewChat = useCallback(async (): Promise<string | null> => {
    try {
      const data = await apiRequest<{ id: string }>("/chats", {
        method: "POST",
        body: { title: "Voice Brainstorm" },
      });
      setChatOptions((prev) => [{ id: data.id, title: "Voice Brainstorm" }, ...prev]);
      setSelectedChatId(data.id);
      return data.id;
    } catch (err) {
      console.warn("[VoiceAgent] Failed to create chat:", err);
      return null;
    }
  }, []);

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  const cancelRelisten = useCallback(() => {
    if (relistenTimerRef.current) {
      clearTimeout(relistenTimerRef.current);
      relistenTimerRef.current = null;
    }
  }, []);

  const startListeningRef = useRef<(() => Promise<void>) | undefined>(undefined);

  const startListening = useCallback(async () => {
    cancelRelisten();
    setErrorMessage(null);
    setErrorSource(null);
    lastSubmitTimeRef.current = 0; // Reset debounce so next submission is always accepted
    setVoiceState("LISTENING");
    await stt.start();
  }, [stt, cancelRelisten]);

  // Keep ref in sync for use in setTimeout callbacks
  useEffect(() => { startListeningRef.current = startListening; }, [startListening]);

  /** Schedule auto-relisten after a delay. Timer is cancelled by stopAll/cleanup. */
  const scheduleRelisten = useCallback((delayMs: number) => {
    cancelRelisten();
    relistenTimerRef.current = setTimeout(() => {
      relistenTimerRef.current = null;
      startListeningRef.current?.();
    }, delayMs);
  }, [cancelRelisten]);

  const stopAll = useCallback(() => {
    cancelRelisten();
    stt.stop();
    sseAbortRef.current?.abort();
    setVoiceState("IDLE");
    impactLight();
  }, [stt, cancelRelisten]);

  const retryFromError = useCallback(() => {
    setErrorMessage(null);
    setErrorSource(null);
    startListening();
  }, [startListening]);

  // -------------------------------------------------------------------------
  // Chat picker
  // -------------------------------------------------------------------------

  const showChatPicker = useCallback(() => {
    const options = ["+ New Chat", ...chatOptions.map((c) => c.title), "Cancel"];
    const cancelIndex = options.length - 1;

    if (Platform.OS === "ios") {
      ActionSheetIOS.showActionSheetWithOptions(
        { options, cancelButtonIndex: cancelIndex, title: "Select Chat" },
        (index) => {
          if (index === cancelIndex) return;
          if (index === 0) {
            setSelectedChatId(NEW_CHAT_ID);
          } else {
            setSelectedChatId(chatOptions[index - 1].id);
          }
          impactLight();
        },
      );
    } else {
      const currentIdx = chatOptions.findIndex((c) => c.id === selectedChatId);
      if (currentIdx < 0 || currentIdx >= chatOptions.length - 1) {
        setSelectedChatId(NEW_CHAT_ID);
      } else {
        setSelectedChatId(chatOptions[currentIdx + 1].id);
      }
    }
  }, [chatOptions, selectedChatId]);

  // -------------------------------------------------------------------------
  // SSE: Send transcript to backend
  // -------------------------------------------------------------------------

  const sendToAgent = useCallback(
    async (userText: string) => {
      const token = getDeviceToken();
      if (!token) {
        setVoiceState("ERROR");
        setErrorMessage("No device token. Check settings.");
        setErrorSource("agent");
        notificationError();
        return;
      }

      const now = Date.now();
      if (now - lastSubmitTimeRef.current < SUBMIT_DEBOUNCE_MS) return;
      lastSubmitTimeRef.current = now;

      if (userText.trim().length < MIN_TRANSCRIPT_LENGTH) {
        // Brief feedback, then auto-restart (tracked timer for proper cleanup)
        setVoiceState("ERROR");
        setErrorMessage("Didn't catch that — try again");
        setErrorSource("stt");
        scheduleRelisten(1500);
        return;
      }

      // Resolve chat_id
      let chatId = activeChatIdRef.current;
      if (chatId === NEW_CHAT_ID) {
        const newId = await createNewChat();
        if (!newId) {
          setVoiceState("ERROR");
          setErrorMessage("Failed to create new chat.");
          setErrorSource("agent");
          notificationError();
          return;
        }
        chatId = newId;
        activeChatIdRef.current = chatId;
      }

      lastUserTextRef.current = userText;
      setEntries((prev) => [...prev, { role: "user", text: userText, key: nextEntryKey() }]);
      setVoiceState("WAITING");
      setCurrentAgentText(null);
      impactMedium(); // Confirm utterance captured

      sseAbortRef.current?.abort();
      const abortController = new AbortController();
      sseAbortRef.current = abortController;

      const timeoutId = setTimeout(() => abortController.abort(), 60_000);

      try {
        const url = `${getApiBaseUrl()}/voice/respond`;
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: chatId, transcript: userText, token }),
          signal: abortController.signal,
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";
        let latestAgentText: string | null = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const event = parseSSELine(line);
            if (!event) continue;

            switch (event.type) {
              case "thinking":
                break;
              case "agent_text":
                latestAgentText = event.text;
                setCurrentAgentText(event.text);
                break;
              case "audio_ready":
                if (latestAgentText) {
                  const text = latestAgentText;
                  setEntries((prev) => [...prev, { role: "assistant", text, key: nextEntryKey() }]);
                  setCurrentAgentText(null);
                }
                // Brief pause so user can read the response before auto-restarting
                scheduleRelisten(AUTO_RELISTEN_DELAY_MS);
                break;
              case "error":
              case "timeout":
                setVoiceState("ERROR");
                setErrorMessage(event.message);
                setErrorSource("agent");
                notificationError();
                return;
            }
          }
        }

        // Stream ended without audio_ready — finalize text
        if (latestAgentText) {
          const text = latestAgentText;
          setEntries((prev) => [...prev, { role: "assistant", text, key: nextEntryKey() }]);
          setCurrentAgentText(null);
          // Brief pause so user can read the response before auto-restarting
          scheduleRelisten(AUTO_RELISTEN_DELAY_MS);
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          if (voiceStateRef.current === "WAITING") {
            setVoiceState("ERROR");
            setErrorMessage("Request timed out. Try again.");
            setErrorSource("agent");
            notificationError();
          }
          return;
        }
        setVoiceState("ERROR");
        setErrorMessage((err as Error).message || "Connection failed. Check WiFi.");
        setErrorSource("agent");
        notificationError();
      } finally {
        clearTimeout(timeoutId);
      }
    },
    [createNewChat, scheduleRelisten],
  );

  /** Explicitly stop STT and send whatever was captured so far.
   *  Reads stt.partial/transcript from latest render — at most one frame behind
   *  the native speech engine, which is acceptable for a manual "send" action. */
  const sendNow = useCallback(() => {
    const text = stt.partial || stt.transcript;
    stt.stop();
    if (text && text.trim().length >= MIN_TRANSCRIPT_LENGTH) {
      sendToAgent(text);
    } else {
      // Text too short — use startListening() to properly reset state and restart STT
      startListening();
    }
  }, [stt, sendToAgent, startListening]);

  // -------------------------------------------------------------------------
  // Effects: Bridge STT events → voice state machine
  // -------------------------------------------------------------------------

  // STT error → voice error
  useEffect(() => {
    if (stt.error && voiceStateRef.current === "LISTENING") {
      setVoiceState("ERROR");
      setErrorMessage(stt.error);
      setErrorSource("stt");
      notificationError();
    }
  }, [stt.error]);

  // STT finished → send to agent
  useEffect(() => {
    if (voiceStateRef.current !== "LISTENING") return;
    if (!stt.isListening && stt.transcript) {
      sendToAgent(stt.transcript);
      stt.reset();
    }
  }, [stt.isListening, stt.transcript, sendToAgent, stt]);

  // Cleanup on tab blur
  useFocusEffect(
    useCallback(() => {
      return () => {
        cancelRelisten();
        stt.stop();
        sseAbortRef.current?.abort();
        setVoiceState("IDLE");
      };
    }, [stt, cancelRelisten]),
  );

  // -------------------------------------------------------------------------
  // Derived
  // -------------------------------------------------------------------------

  const selectedLabel = selectedChatId === NEW_CHAT_ID
    ? "New Chat"
    : chatOptions.find((c) => c.id === selectedChatId)?.title || "Chat";

  return {
    voiceState,
    entries,
    currentAgentText,
    errorMessage,
    errorSource,
    sttPartial: stt.partial,
    sttTranscript: stt.transcript,
    chatOptions,
    selectedChatId,
    selectedLabel,
    showChatPicker,
    startListening,
    sendNow,
    stopAll,
    retryFromError,
  };
}
