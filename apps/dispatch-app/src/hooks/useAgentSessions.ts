import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import {
  getAgentSessions,
  createAgentSession,
  deleteAgentSession,
  renameAgentSession,
} from "../api/agents";
import type { AgentSession } from "../api/types";
import { AGENT_SESSIONS_POLL_INTERVAL } from "../config/constants";
import type { SourceFilter } from "../components/FilterPills";

interface UseAgentSessionsReturn {
  sessions: AgentSession[];
  filteredSessions: AgentSession[];
  isLoading: boolean;
  error: string | null;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  sourceFilter: SourceFilter;
  setSourceFilter: (filter: SourceFilter) => void;
  createSession: (name: string) => Promise<AgentSession | null>;
  deleteSession: (sessionId: string) => Promise<boolean>;
  renameSession: (sessionId: string, name: string) => Promise<boolean>;
  refresh: () => Promise<void>;
}

export function useAgentSessions(): UseAgentSessionsReturn {
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");

  const mountedRef = useRef(true);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // -----------------------------------------------------------------------
  // Load sessions
  // -----------------------------------------------------------------------

  const loadSessions = useCallback(async () => {
    try {
      const fetched = await getAgentSessions();
      if (mountedRef.current) {
        setSessions(fetched);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(
          err instanceof Error ? err.message : "Failed to load sessions",
        );
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  // -----------------------------------------------------------------------
  // Polling
  // -----------------------------------------------------------------------

  const startPolling = useCallback(() => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(() => {
      loadSessions();
    }, AGENT_SESSIONS_POLL_INTERVAL);
  }, [loadSessions]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Filtered sessions
  // -----------------------------------------------------------------------

  const filteredSessions = sessions.filter((s) => {
    // Source filter
    if (sourceFilter !== "all") {
      if (s.source.toLowerCase() !== sourceFilter) return false;
    }

    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      if (
        !s.name.toLowerCase().includes(q) &&
        !(s.last_message && s.last_message.toLowerCase().includes(q))
      )
        return false;
    }

    return true;
  });

  // -----------------------------------------------------------------------
  // CRUD
  // -----------------------------------------------------------------------

  const createSession = useCallback(
    async (name: string): Promise<AgentSession | null> => {
      try {
        const result = await createAgentSession(name);
        // Refresh list to get full session object
        await loadSessions();
        // Return a synthetic AgentSession for navigation
        return {
          id: result.id,
          type: "dispatch-api",
          name: result.name,
          tier: "",
          source: "dispatch-api",
          chat_type: "individual",
          participants: null,
          last_message: null,
          last_message_time: null,
          last_message_is_from_me: false,
          status: result.status,
        };
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof Error ? err.message : "Failed to create session",
          );
        }
        return null;
      }
    },
    [loadSessions],
  );

  const deleteSession = useCallback(
    async (sessionId: string): Promise<boolean> => {
      try {
        await deleteAgentSession(sessionId, true);
        if (mountedRef.current) {
          setSessions((prev) => prev.filter((s) => s.id !== sessionId));
        }
        return true;
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof Error ? err.message : "Failed to delete session",
          );
        }
        return false;
      }
    },
    [],
  );

  const renameSession = useCallback(
    async (sessionId: string, name: string): Promise<boolean> => {
      try {
        await renameAgentSession(sessionId, name);
        if (mountedRef.current) {
          setSessions((prev) =>
            prev.map((s) => (s.id === sessionId ? { ...s, name } : s)),
          );
        }
        return true;
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof Error ? err.message : "Failed to rename session",
          );
        }
        return false;
      }
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Refresh (pull to refresh)
  // -----------------------------------------------------------------------

  const refresh = useCallback(async () => {
    setIsLoading(true);
    await loadSessions();
  }, [loadSessions]);

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  // Initial load + start polling
  useEffect(() => {
    loadSessions().then(() => {
      if (mountedRef.current) startPolling();
    });

    return () => {
      stopPolling();
    };
  }, [loadSessions, startPolling, stopPolling]);

  // Pause polling when app backgrounds
  useEffect(() => {
    const handleAppState = (nextState: AppStateStatus) => {
      if (nextState === "active") {
        loadSessions();
        startPolling();
      } else {
        stopPolling();
      }
    };
    const sub = AppState.addEventListener("change", handleAppState);
    return () => sub.remove();
  }, [loadSessions, startPolling, stopPolling]);

  // Cleanup
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return {
    sessions,
    filteredSessions,
    isLoading,
    error,
    searchQuery,
    setSearchQuery,
    sourceFilter,
    setSourceFilter,
    createSession,
    deleteSession,
    renameSession,
    refresh,
  };
}
