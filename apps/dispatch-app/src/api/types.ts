/** A message in a dispatch-api chat conversation */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  audio_url: string | null;
  image_url: string | null;
  created_at: string;
  status?: string; // "generating" | "complete" | "failed"
  failure_reason?: string | null; // "timeout" | "generation_error" | "server_restart" | "storage_error"
}

/** A chat conversation (dispatch-api chats) */
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message: string | null;
  last_message_at: string | null;
  last_message_role: string | null;
  last_opened_at: string | null;
  has_notes?: boolean;
  is_thinking?: boolean;
  forked_from?: string | null;
  fork_message_id?: string | null;
  marked_unread?: boolean;
  image_url?: string | null; // Cover image URL (generated via nano-banana)
}

/** Notes for a chat */
export interface ChatNotes {
  chat_id: string;
  content: string;
  updated_at: string | null;
}

/** Response from POST /prompt and POST /prompt-with-image */
export interface PromptResponse {
  status: string;
  message: string;
  request_id: string;
}

/** An agent/contact session from the agents dashboard API */
export interface AgentSession {
  id: string;
  type: "contact" | "dispatch-api";
  name: string;
  tier: string;
  source: string;
  chat_type: string;
  participants: string[] | null;
  last_message: string | null;
  last_message_time: string | null;
  last_message_is_from_me: boolean;
  status: string;
}

/** A message in an agent/contact session */
export interface AgentMessage {
  id: string;
  role: string;
  text: string;
  sender: string;
  is_from_me: boolean;
  timestamp_ms: number;
  source: string;
  has_attachment: boolean;
}

/** Response from GET /messages (chat messages) */
export interface MessagesResponse {
  messages: ChatMessage[];
  is_thinking?: boolean;
}

/** Response from GET /chats */
export interface ChatsResponse {
  chats: Conversation[];
}

/** Response from GET /api/agents/sessions */
export interface AgentSessionsResponse {
  sessions: AgentSession[];
}

/** Response from GET /api/agents/messages */
export interface AgentMessagesResponse {
  messages: AgentMessage[];
  has_more: boolean;
  is_thinking: boolean;
}

/** An SDK event from the agent session */
export interface SdkEvent {
  id: number;
  timestamp: number;
  session_name: string;
  chat_id: string | null;
  event_type: string;
  tool_name: string | null;
  tool_use_id: string | null;
  duration_ms: number | null;
  is_error: boolean;
  payload: string | null;
  num_turns: number | null;
}

/** Response from GET /api/agents/sdk-events */
export interface SdkEventsResponse {
  events: SdkEvent[];
}
