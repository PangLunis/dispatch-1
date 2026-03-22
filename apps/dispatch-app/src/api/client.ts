import { getApiBaseUrl, REQUEST_TIMEOUT } from "../config/constants";

/** Token stored in memory after loading from secure store */
let _deviceToken: string | null = null;

/** Set the device token (called by useDeviceToken hook on app start) */
export function setDeviceToken(token: string): void {
  _deviceToken = token;
}

/** Get the current device token */
export function getDeviceToken(): string | null {
  return _deviceToken;
}

/** API error with status code and response body */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    message?: string,
  ) {
    super(message || `API error ${status}: ${body}`);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  timeout?: number;
  /** Skip adding auth token to request */
  skipAuth?: boolean;
}

/**
 * Base fetch wrapper for dispatch-api.
 *
 * - Adds auth token as query param (matching existing API convention)
 * - Handles timeouts via AbortController
 * - Parses JSON responses
 * - Throws ApiError on non-2xx responses
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    params = {},
    timeout = REQUEST_TIMEOUT,
    skipAuth = false,
  } = options;

  // Build URL with query params
  const url = new URL(path, getApiBaseUrl());

  // Add auth token if available
  if (!skipAuth && _deviceToken) {
    url.searchParams.set("token", _deviceToken);
  }

  // Add additional params
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value));
    }
  }

  // Set up abort controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const headers: Record<string, string> = {};
    let requestBody: string | FormData | undefined;

    if (body !== undefined) {
      if (body instanceof FormData) {
        requestBody = body;
        // Don't set Content-Type for FormData — browser sets it with boundary
      } else {
        headers["Content-Type"] = "application/json";
        requestBody = JSON.stringify(body);
      }
    }

    const response = await fetch(url.toString(), {
      method,
      headers,
      body: requestBody,
      signal: controller.signal,
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new ApiError(response.status, text);
    }

    // Handle empty responses (204 No Content, etc.)
    const contentType = response.headers.get("content-type") ?? "";
    if (
      response.status === 204 ||
      !contentType.includes("application/json")
    ) {
      return {} as T;
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if ((error as Error).name === "AbortError") {
      throw new ApiError(0, "Request timed out");
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}
