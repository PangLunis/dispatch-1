import { apiRequest } from "./client";
import { generateUUID } from "../utils/uuid";
import type {
  AgentSessionsResponse,
  AgentMessagesResponse,
  AgentSession,
  Conversation,
  SdkEventsResponse,
} from "./types";

/** List all sessions (contact + agent). GET /api/agents/sessions */
export async function getAgentSessions(): Promise<AgentSession[]> {
  const res = await apiRequest<AgentSessionsResponse>(
    "/api/agents/sessions",
  );
  return res.sessions;
}

/** Get messages for a session. GET /api/agents/messages */
export async function getAgentMessages(
  sessionId: string,
  options?: {
    limit?: number;
    before_ts?: number;
    after_ts?: number;
  },
): Promise<AgentMessagesResponse> {
  return apiRequest<AgentMessagesResponse>("/api/agents/messages", {
    params: {
      session_id: sessionId,
      limit: options?.limit,
      before_ts: options?.before_ts,
      after_ts: options?.after_ts,
    },
  });
}

/** Create a new agent session. POST /api/agents/sessions */
export async function createAgentSession(
  name: string,
): Promise<{ id: string; name: string; status: string }> {
  return apiRequest<{ id: string; name: string; status: string }>(
    "/api/agents/sessions",
    {
      method: "POST",
      body: { name },
    },
  );
}

/** Send a message to a session. POST /api/agents/messages */
export async function sendAgentMessage(
  sessionId: string,
  text: string,
  messageId?: string,
): Promise<{ ok: boolean; message_id?: string }> {
  return apiRequest<{ ok: boolean; message_id?: string }>(
    "/api/agents/messages",
    {
      method: "POST",
      body: { session_id: sessionId, text, message_id: messageId ?? generateUUID() },
    },
  );
}

/** Get SDK events for a session. GET /api/agents/sdk-events */
export async function getAgentSdkEvents(
  sessionId: string,
  options?: {
    limit?: number;
    since_id?: number;
    since_ts?: number;
  },
): Promise<SdkEventsResponse> {
  return apiRequest<SdkEventsResponse>("/api/agents/sdk-events", {
    params: {
      session_id: sessionId,
      limit: options?.limit,
      since_id: options?.since_id,
      since_ts: options?.since_ts,
    },
  });
}

/** Rename an agent session. PATCH /api/agents/sessions/:sessionId */
export async function renameAgentSession(
  sessionId: string,
  name: string,
): Promise<{ ok: boolean; id: string; name: string }> {
  return apiRequest<{ ok: boolean; id: string; name: string }>(
    `/api/agents/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      body: { name },
    },
  );
}

/** Fork an agent session into a new dispatch-app chat. POST /api/agents/sessions/:sessionId/fork-to-chat */
export async function forkAgentToChat(
  sessionId: string,
  title: string,
): Promise<Conversation> {
  return apiRequest<Conversation>(
    `/api/agents/sessions/${encodeURIComponent(sessionId)}/fork-to-chat`,
    {
      method: "POST",
      body: { title },
    },
  );
}

/** Delete an agent session. DELETE /api/agents/sessions/:sessionId */
export async function deleteAgentSession(
  sessionId: string,
  deleteMessages: boolean = false,
): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(
    `/api/agents/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "DELETE",
      params: { delete_messages: deleteMessages },
    },
  );
}
