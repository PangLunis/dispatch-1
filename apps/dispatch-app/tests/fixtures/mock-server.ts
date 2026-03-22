/**
 * Playwright route handler setup for full network isolation.
 *
 * Intercepts ALL requests to the API origin and returns mock data.
 * Supports dynamic scenario switching (normal / empty / error).
 */

import type { Page, Route } from "@playwright/test";
import {
  MOCK_CHATS,
  MOCK_NEW_CHAT,
  MOCK_MESSAGES,
  MOCK_SESSIONS,
  MOCK_NEW_SESSION,
  MOCK_AGENT_MESSAGES,
  MOCK_SDK_EVENTS,
  MOCK_LOG_LINES,
} from "./mock-data";

// ---------------------------------------------------------------------------
// Scenario state — controls which mock data is returned
// ---------------------------------------------------------------------------

export type Scenario = "normal" | "empty" | "error" | "thinking";

interface MockState {
  chats: Scenario;
  messages: Scenario;
  sessions: Scenario;
  agentMessages: Scenario;
  sdkEvents: Scenario;
  logs: Scenario;
  /** Per-endpoint error overrides: path prefix -> true to force 500 */
  errorEndpoints: Set<string>;
}

function defaultState(): MockState {
  return {
    chats: "normal",
    messages: "normal",
    sessions: "normal",
    agentMessages: "normal",
    sdkEvents: "normal",
    logs: "normal",
    errorEndpoints: new Set(),
  };
}

// ---------------------------------------------------------------------------
// Tiny WAV file (44 bytes) for audio route mocks
// ---------------------------------------------------------------------------

const MOCK_WAV_HEADER = Buffer.from([
  // RIFF header
  0x52, 0x49, 0x46, 0x46, // "RIFF"
  0x24, 0x00, 0x00, 0x00, // file size - 8
  0x57, 0x41, 0x56, 0x45, // "WAVE"
  // fmt subchunk
  0x66, 0x6d, 0x74, 0x20, // "fmt "
  0x10, 0x00, 0x00, 0x00, // subchunk size (16)
  0x01, 0x00,             // PCM
  0x01, 0x00,             // mono
  0x44, 0xac, 0x00, 0x00, // 44100 Hz
  0x88, 0x58, 0x01, 0x00, // byte rate
  0x02, 0x00,             // block align
  0x10, 0x00,             // bits per sample
  // data subchunk
  0x64, 0x61, 0x74, 0x61, // "data"
  0x00, 0x00, 0x00, 0x00, // data size (0 = silence)
]);

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

function handleRoute(state: MockState, route: Route) {
  const url = new URL(route.request().url());
  const method = route.request().method();
  const path = url.pathname;

  // Check per-endpoint error override
  for (const ep of state.errorEndpoints) {
    if (path.startsWith(ep) || path.includes(ep)) {
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "Mock error" }),
      });
    }
  }

  // -----------------------------------------------------------------------
  // Health
  // -----------------------------------------------------------------------
  if (path === "/health" || path.endsWith("/health")) {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok" }),
    });
  }

  // -----------------------------------------------------------------------
  // Chats
  // -----------------------------------------------------------------------
  if (path === "/chats" && method === "GET") {
    if (state.chats === "error") {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Server error" }) });
    }
    const chats = state.chats === "empty" ? [] : MOCK_CHATS;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ chats }),
    });
  }

  if (path === "/chats" && method === "POST") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_NEW_CHAT),
    });
  }

  // PATCH /chats/:id
  if (path.match(/^\/chats\/[^/]+$/) && method === "PATCH") {
    const chatId = path.split("/").pop()!;
    let body: { title?: string } = {};
    try {
      const reqBody = route.request().postData();
      if (reqBody) body = JSON.parse(reqBody);
    } catch {}
    const chat = MOCK_CHATS.find((c) => c.id === chatId) ?? MOCK_CHATS[0];
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...chat, title: body.title ?? chat.title }),
    });
  }

  // DELETE /chats/:id
  if (path.match(/^\/chats\/[^/]+$/) && method === "DELETE") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  }

  // POST /chats/:id/open
  if (path.match(/^\/chats\/[^/]+\/open$/) && method === "POST") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok" }),
    });
  }

  // -----------------------------------------------------------------------
  // Messages
  // -----------------------------------------------------------------------
  if (path === "/messages" && method === "GET") {
    if (state.messages === "error") {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Server error" }) });
    }
    const messages = state.messages === "empty" ? [] : MOCK_MESSAGES;
    const isThinking = state.messages === "thinking";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ messages, is_thinking: isThinking }),
    });
  }

  if (path === "/messages" && method === "DELETE") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", message: "cleared" }),
    });
  }

  // -----------------------------------------------------------------------
  // Prompt
  // -----------------------------------------------------------------------
  if (path === "/prompt" && method === "POST") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", message: "queued", request_id: "mock-req-123" }),
    });
  }

  if (path === "/prompt-with-image" && method === "POST") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", message: "queued", request_id: "mock-req-img-456" }),
    });
  }

  // -----------------------------------------------------------------------
  // Restart session
  // -----------------------------------------------------------------------
  if (path === "/restart-session" && method === "POST") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", message: "restarted" }),
    });
  }

  // -----------------------------------------------------------------------
  // Audio
  // -----------------------------------------------------------------------
  if (path.startsWith("/audio/")) {
    return route.fulfill({
      status: 200,
      contentType: "audio/wav",
      body: MOCK_WAV_HEADER,
    });
  }

  // -----------------------------------------------------------------------
  // Images (static mock)
  // -----------------------------------------------------------------------
  if (path.startsWith("/images/")) {
    // 1x1 transparent PNG
    const PNG_1x1 = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB" +
      "Nl7BcQAAAABJRU5ErkJggg==",
      "base64",
    );
    return route.fulfill({
      status: 200,
      contentType: "image/png",
      body: PNG_1x1,
    });
  }

  // -----------------------------------------------------------------------
  // Agent sessions
  // -----------------------------------------------------------------------
  if (path === "/api/agents/sessions" && method === "GET") {
    if (state.sessions === "error") {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Server error" }) });
    }
    const sessions = state.sessions === "empty" ? [] : MOCK_SESSIONS;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions }),
    });
  }

  if (path === "/api/agents/sessions" && method === "POST") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_NEW_SESSION),
    });
  }

  // PATCH /api/agents/sessions/:id
  if (path.match(/^\/api\/agents\/sessions\/[^/]+$/) && method === "PATCH") {
    let body: { name?: string } = {};
    try {
      const reqBody = route.request().postData();
      if (reqBody) body = JSON.parse(reqBody);
    } catch {}
    const sessionId = decodeURIComponent(path.split("/").pop()!);
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, id: sessionId, name: body.name ?? "Renamed Session" }),
    });
  }

  // DELETE /api/agents/sessions/:id
  if (path.match(/^\/api\/agents\/sessions\/[^/]+$/) && method === "DELETE") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  }

  // -----------------------------------------------------------------------
  // Agent messages
  // -----------------------------------------------------------------------
  if (path === "/api/agents/messages" && method === "GET") {
    if (state.agentMessages === "error") {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Server error" }) });
    }
    const messages = state.agentMessages === "empty" ? [] : MOCK_AGENT_MESSAGES;
    const isThinking = state.agentMessages === "thinking";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ messages, has_more: false, is_thinking: isThinking }),
    });
  }

  if (path === "/api/agents/messages" && method === "POST") {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, message_id: "mock-amsg-new" }),
    });
  }

  // -----------------------------------------------------------------------
  // SDK events
  // -----------------------------------------------------------------------
  if (path === "/api/agents/sdk-events" && method === "GET") {
    if (state.sdkEvents === "error") {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Server error" }) });
    }
    const events = state.sdkEvents === "empty" ? [] : MOCK_SDK_EVENTS;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ events }),
    });
  }

  // -----------------------------------------------------------------------
  // Logs
  // -----------------------------------------------------------------------
  if (path === "/api/dashboard/logs" && method === "GET") {
    if (state.logs === "error") {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Server error" }) });
    }
    const lines = state.logs === "empty" ? [] : MOCK_LOG_LINES;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        lines,
        total_lines: lines.length,
        returned_from_line: 0,
      }),
    });
  }

  // -----------------------------------------------------------------------
  // Dashboard HTML (fallback for WebView)
  // -----------------------------------------------------------------------
  if (path === "/dashboard" || path.startsWith("/dashboard")) {
    return route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<html><body><h1>Mock Dashboard</h1></body></html>",
    });
  }

  // -----------------------------------------------------------------------
  // Fallback: let app static assets through but block unknown API calls
  // -----------------------------------------------------------------------
  if (path.startsWith("/api/") || path === "/chats" || path === "/messages" || path === "/prompt") {
    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: `Unknown mock route: ${method} ${path}` }),
    });
  }

  // Let through (static assets, JS bundles, etc.)
  return route.continue();
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface MockServer {
  /** Current state — mutate directly to change scenarios between tests */
  state: MockState;
  /** Set a specific endpoint to error mode */
  setError(endpointPrefix: string): void;
  /** Clear an endpoint error override */
  clearError(endpointPrefix: string): void;
  /** Reset all state to defaults */
  reset(): void;
}

/**
 * Set up mock API routes on a Playwright page.
 * Call this BEFORE navigating to the app.
 *
 * Returns a MockServer object for controlling scenarios.
 */
export async function setupMockServer(page: Page): Promise<MockServer> {
  const state = defaultState();

  // Intercept all requests to the same origin (the app is served from the API server)
  await page.route("**/*", (route) => {
    const url = route.request().url();
    // Only intercept API-like paths, let static assets through
    const parsed = new URL(url);
    const path = parsed.pathname;

    const isApiPath =
      path === "/chats" ||
      path.startsWith("/chats/") ||
      path === "/messages" ||
      path === "/prompt" ||
      path === "/prompt-with-image" ||
      path === "/restart-session" ||
      path === "/health" ||
      path.startsWith("/audio/") ||
      path.startsWith("/images/") ||
      path.startsWith("/api/") ||
      path === "/dashboard" ||
      path.startsWith("/dashboard");

    if (isApiPath) {
      return handleRoute(state, route);
    }

    return route.continue();
  });

  const server: MockServer = {
    state,
    setError(endpointPrefix: string) {
      state.errorEndpoints.add(endpointPrefix);
    },
    clearError(endpointPrefix: string) {
      state.errorEndpoints.delete(endpointPrefix);
    },
    reset() {
      state.chats = "normal";
      state.messages = "normal";
      state.sessions = "normal";
      state.agentMessages = "normal";
      state.sdkEvents = "normal";
      state.logs = "normal";
      state.errorEndpoints.clear();
    },
  };

  return server;
}
