import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { getAgentSdkEvents } from "../api/agents";
import type { SdkEvent } from "../api/types";

const POLL_INTERVAL = 2000;

export interface UseSdkEventsReturn {
  events: SdkEvent[];
  isLoading: boolean;
  error: string | null;
  /** True when the last SDK event is a "result" (turn complete) */
  isComplete: boolean;
  refresh: () => Promise<void>;
}

/**
 * Stateless SDK events hook — fetches ALL events since `sinceTs` on every poll.
 * This means navigating away and back shows the full event history for the
 * current turn, not just events that arrived while on screen.
 */
export function useSdkEvents(
  sessionId: string,
  enabled: boolean,
  /** Timestamp (ms) to fetch events after. Typically the last user message time. */
  sinceTs?: number,
): UseSdkEventsReturn {
  const [events, setEvents] = useState<SdkEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);

  const mountedRef = useRef(true);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sinceTsRef = useRef(sinceTs);
  sinceTsRef.current = sinceTs;

  /**
   * Fetch all events since the cutoff timestamp.
   * Replaces the entire events array each time for true statelessness.
   */
  const fetchEvents = useCallback(async () => {
    try {
      const res = await getAgentSdkEvents(sessionId, {
        since_ts: sinceTsRef.current,
        limit: 200,
      });
      if (!mountedRef.current) return;

      // Server returns newest-first, reverse for chronological order
      const sorted = [...res.events].reverse();
      setEvents(sorted);

      // Check if the newest event is a "result" (turn complete)
      if (res.events.length > 0 && res.events[0].event_type === "result") {
        setIsComplete(true);
      } else {
        setIsComplete(false);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      // Only set error on first load, silently ignore poll errors
      if (events.length === 0) {
        setError(
          err instanceof Error ? err.message : "Failed to load events",
        );
      }
    }
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const startPolling = useCallback(() => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(fetchEvents, POLL_INTERVAL);
  }, [fetchEvents]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    await fetchEvents();
    setIsLoading(false);
  }, [fetchEvents]);

  // Main effect: start/stop based on enabled
  useEffect(() => {
    if (!enabled) {
      stopPolling();
      setEvents([]);
      setIsComplete(false);
      return;
    }

    mountedRef.current = true;
    setIsLoading(true);
    fetchEvents().then(() => {
      if (mountedRef.current) {
        setIsLoading(false);
        startPolling();
      }
    });

    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [enabled, fetchEvents, startPolling, stopPolling]);

  // When sinceTs changes (new message sent), do an immediate fetch
  useEffect(() => {
    if (!enabled || sinceTs === undefined) return;
    setIsComplete(false);
    fetchEvents();
  }, [sinceTs]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pause/resume on app state change
  useEffect(() => {
    if (!enabled) return;
    const handleAppState = (nextState: AppStateStatus) => {
      if (nextState === "active") {
        fetchEvents();
        startPolling();
      } else {
        stopPolling();
      }
    };
    const sub = AppState.addEventListener("change", handleAppState);
    return () => sub.remove();
  }, [enabled, fetchEvents, startPolling, stopPolling]);

  return { events, isLoading, error, isComplete, refresh };
}
