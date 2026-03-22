import { useEffect, useState } from "react";
import { setDeviceToken, apiRequest } from "../api/client";
import * as storage from "../utils/storage";
import { generateUUID } from "../utils/uuid";

const DEVICE_TOKEN_KEY = "dispatch_device_token";
const TOKEN_REGISTERED_KEY = "dispatch_device_token_registered";

/**
 * Register the device token with the server.
 * Idempotent — safe to call multiple times.
 */
async function registerToken(token: string): Promise<void> {
  try {
    // Check if we already registered this token
    const registered = await storage.getItem(TOKEN_REGISTERED_KEY);
    if (registered === token) return;

    await apiRequest("/register", {
      method: "POST",
      params: { token },
      skipAuth: true,
    });
    await storage.setItem(TOKEN_REGISTERED_KEY, token);
  } catch {
    // Registration failed — will retry on next app load
  }
}

/**
 * Hook that loads or generates a persistent device token on first launch.
 * The token is stored in secure storage (Keychain on iOS, localStorage on web)
 * and set on the API client for all subsequent requests.
 *
 * Automatically registers the token with the server on first use.
 *
 * Returns { token, isLoading } — token is null while loading.
 */
export function useDeviceToken(): {
  token: string | null;
  isLoading: boolean;
} {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function loadOrCreateToken() {
      try {
        let storedToken = await storage.getItem(DEVICE_TOKEN_KEY);

        if (!storedToken) {
          storedToken = generateUUID();
          await storage.setItem(DEVICE_TOKEN_KEY, storedToken);
        }

        // Set on the API client so all requests include it
        setDeviceToken(storedToken);

        // Register with the server (idempotent)
        await registerToken(storedToken);

        if (mounted) {
          setToken(storedToken);
        }
      } catch (error) {
        // If storage fails, generate an ephemeral token
        const ephemeral = generateUUID();
        setDeviceToken(ephemeral);
        // Try to register ephemeral token too
        registerToken(ephemeral);
        if (mounted) {
          setToken(ephemeral);
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    loadOrCreateToken();

    return () => {
      mounted = false;
    };
  }, []);

  return { token, isLoading };
}
