import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { getDashboardHealth, getDashboardCcu } from "../api/dashboard";
import type { DashboardHealth, DashboardCcuResponse } from "../api/types";

const HEALTH_POLL_INTERVAL = 10_000; // 10 seconds
const CCU_POLL_INTERVAL = 60_000; // 60 seconds
const DEBOUNCE_MS = 3_000; // skip fetch if last was <3s ago

interface UseDashboardReturn {
  health: DashboardHealth | null;
  ccu: DashboardCcuResponse | null;
  isLoading: boolean;
  ccuLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
  refreshCcu: () => Promise<void>;
}

/**
 * Hook that fetches dashboard health + CCU data for the main dashboard screen.
 *
 * - Health polls every 10s when the tab is focused and app is in foreground
 * - CCU polls every 60s (separate interval)
 * - Pauses on background / tab blur
 * - Caches last successful data (stale-while-revalidate)
 * - Debounces rapid focus events
 * - refreshCcu() for tap-to-reload quota
 */
export function useDashboard(): UseDashboardReturn {
  const [health, setHealth] = useState<DashboardHealth | null>(null);
  const [ccu, setCcu] = useState<DashboardCcuResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [ccuLoading, setCcuLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const mountedRef = useRef(true);
  const healthPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const ccuPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastHealthFetchRef = useRef<number>(0);
  const lastCcuFetchRef = useRef<number>(0);
  const isFocusedRef = useRef(false);

  // -----------------------------------------------------------------------
  // Fetch health data
  // -----------------------------------------------------------------------

  const fetchHealth = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastHealthFetchRef.current < DEBOUNCE_MS) return;

    try {
      const healthData = await getDashboardHealth();
      if (!mountedRef.current) return;
      setHealth(healthData);
      setError(null);
      setLastUpdated(new Date());
      lastHealthFetchRef.current = Date.now();
    } catch (err) {
      if (!mountedRef.current) return;
      setError(
        err instanceof Error ? err.message : "Failed to load dashboard",
      );
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  // -----------------------------------------------------------------------
  // Fetch CCU/quota data
  // -----------------------------------------------------------------------

  const fetchCcu = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastCcuFetchRef.current < DEBOUNCE_MS) return;

    try {
      if (force) setCcuLoading(true);
      const ccuData = await getDashboardCcu();
      if (!mountedRef.current) return;
      setCcu(ccuData);
      lastCcuFetchRef.current = Date.now();
    } catch {
      // CCU errors are non-critical — don't set main error
    } finally {
      if (mountedRef.current) setCcuLoading(false);
    }
  }, []);

  // -----------------------------------------------------------------------
  // Combined initial fetch
  // -----------------------------------------------------------------------

  const fetchAll = useCallback(
    async (force = false) => {
      await Promise.all([fetchHealth(force), fetchCcu(force)]);
    },
    [fetchHealth, fetchCcu],
  );

  // -----------------------------------------------------------------------
  // Polling
  // -----------------------------------------------------------------------

  const startPolling = useCallback(() => {
    if (!healthPollingRef.current) {
      healthPollingRef.current = setInterval(() => {
        if (isFocusedRef.current) fetchHealth();
      }, HEALTH_POLL_INTERVAL);
    }
    if (!ccuPollingRef.current) {
      ccuPollingRef.current = setInterval(() => {
        if (isFocusedRef.current) fetchCcu();
      }, CCU_POLL_INTERVAL);
    }
  }, [fetchHealth, fetchCcu]);

  const stopPolling = useCallback(() => {
    if (healthPollingRef.current) {
      clearInterval(healthPollingRef.current);
      healthPollingRef.current = null;
    }
    if (ccuPollingRef.current) {
      clearInterval(ccuPollingRef.current);
      ccuPollingRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Focus management — poll only when this tab is visible
  // -----------------------------------------------------------------------

  useFocusEffect(
    useCallback(() => {
      isFocusedRef.current = true;
      fetchAll(); // immediate fetch on focus
      startPolling();

      return () => {
        isFocusedRef.current = false;
        stopPolling();
      };
    }, [fetchAll, startPolling, stopPolling]),
  );

  // -----------------------------------------------------------------------
  // AppState — pause on background
  // -----------------------------------------------------------------------

  useEffect(() => {
    const handleAppState = (nextState: AppStateStatus) => {
      if (nextState === "active" && isFocusedRef.current) {
        fetchAll();
        startPolling();
      } else {
        stopPolling();
      }
    };
    const sub = AppState.addEventListener("change", handleAppState);
    return () => sub.remove();
  }, [fetchAll, startPolling, stopPolling]);

  // -----------------------------------------------------------------------
  // Pull-to-refresh (force fetch all, ignores debounce)
  // -----------------------------------------------------------------------

  const refresh = useCallback(async () => {
    setIsLoading(true);
    await fetchAll(true);
  }, [fetchAll]);

  // -----------------------------------------------------------------------
  // Tap-to-refresh CCU (force fetch CCU only, ignores debounce)
  // -----------------------------------------------------------------------

  const refreshCcu = useCallback(async () => {
    await fetchCcu(true);
  }, [fetchCcu]);

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return { health, ccu, isLoading, ccuLoading, error, lastUpdated, refresh, refreshCcu };
}
