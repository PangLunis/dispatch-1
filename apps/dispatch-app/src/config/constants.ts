import { Platform } from "react-native";
import Constants from "expo-constants";

/**
 * API base URL for dispatch-api.
 *
 * On native, this is configurable at runtime via Settings.
 * The URL is persisted in secure storage and can be changed without rebuilding.
 *
 * On web, it always uses same-origin since the web build is served by dispatch-api.
 */

/** In-memory API base URL — mutable at runtime */
let _apiBaseUrl: string = getDefaultApiBaseUrl();

function getDefaultApiBaseUrl(): string {
  if (Platform.OS === "web") {
    // Same-origin — web build is served by dispatch-api
    return typeof window !== "undefined" ? window.location.origin : "";
  }

  // Native: check for DEV mode (simulator uses localhost)
  if (__DEV__) {
    return "http://localhost:9091";
  }

  // Production native: use apiHost from app config as default
  const apiHost = Constants.expoConfig?.extra?.apiHost as string | undefined;
  if (apiHost) {
    return `http://${apiHost}`;
  }

  // Fallback — should be configured via app.yaml apiHost
  return "http://localhost:9091";
}

/** Get the current API base URL */
export function getApiBaseUrl(): string {
  return _apiBaseUrl;
}

/** Set the API base URL at runtime (called from Settings after loading from storage) */
export function setApiBaseUrl(url: string): void {
  _apiBaseUrl = url;
}

/** Get the default/baked-in API base URL */
export function getDefaultUrl(): string {
  return getDefaultApiBaseUrl();
}

/**
 * @deprecated Use getApiBaseUrl() instead for dynamic URL support.
 * Kept for backward compatibility during migration.
 */
export const API_BASE_URL = getDefaultApiBaseUrl();

/** Polling interval for message updates (ms) */
export const MESSAGE_POLL_INTERVAL = 1500;

/** Polling interval for agent sessions list (ms) */
export const AGENT_SESSIONS_POLL_INTERVAL = 5000;

/** Request timeout (ms) */
export const REQUEST_TIMEOUT = 15000;

/** Storage key for persisted API URL */
export const API_URL_STORAGE_KEY = "dispatch_api_url";
