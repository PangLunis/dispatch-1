/**
 * Mock data for Dispatch App E2E tests.
 *
 * Exports mock chats, messages, sessions, agent messages, SDK events, and logs
 * in normal, empty, error, and thinking states.
 *
 * Status values match the actual codebase: active, idle, error.
 */

import type {
  Conversation,
  ChatMessage,
  AgentSession,
  AgentMessage,
  SdkEvent,
} from "../../src/api/types";

// ---------------------------------------------------------------------------
// Chats
// ---------------------------------------------------------------------------

const now = new Date();
const fiveMinAgo = new Date(now.getTime() - 5 * 60_000).toISOString();
const tenMinAgo = new Date(now.getTime() - 10 * 60_000).toISOString();
const thirtyMinAgo = new Date(now.getTime() - 30 * 60_000).toISOString();
const oneHourAgo = new Date(now.getTime() - 60 * 60_000).toISOString();
const twoHoursAgo = new Date(now.getTime() - 120 * 60_000).toISOString();

export const MOCK_CHATS: Conversation[] = [
  {
    id: "chat-alpha",
    title: "Test Chat Alpha",
    created_at: twoHoursAgo,
    updated_at: fiveMinAgo,
    last_message: "Of course! How can I assist you today?",
    last_message_at: fiveMinAgo,
    last_message_role: "assistant",
    last_opened_at: tenMinAgo, // assistant message is after last_opened => unread
  },
  {
    id: "chat-beta",
    title: "Test Chat Beta",
    created_at: oneHourAgo,
    updated_at: tenMinAgo,
    last_message: "Can you check this for me?",
    last_message_at: tenMinAgo,
    last_message_role: "user",
    last_opened_at: tenMinAgo,
    is_thinking: true,
  },
  {
    id: "chat-gamma",
    title: "Test Chat Gamma",
    created_at: twoHoursAgo,
    updated_at: thirtyMinAgo,
    last_message: "Here is the result you requested.",
    last_message_at: thirtyMinAgo,
    last_message_role: "assistant",
    last_opened_at: fiveMinAgo, // opened after last message => read
  },
];

export const MOCK_NEW_CHAT: Conversation = {
  id: "chat-new",
  title: "New Chat",
  created_at: now.toISOString(),
  updated_at: now.toISOString(),
  last_message: null,
  last_message_at: null,
  last_message_role: null,
  last_opened_at: null,
};

// ---------------------------------------------------------------------------
// Chat Messages (for Chat Alpha)
// ---------------------------------------------------------------------------

const LONG_MESSAGE = "A".repeat(900);

export const MOCK_MESSAGES: ChatMessage[] = [
  {
    id: "msg-1",
    role: "user",
    content: "Hello, can you help me?",
    audio_url: null,
    image_url: null,
    created_at: twoHoursAgo,
  },
  {
    id: "msg-2",
    role: "assistant",
    content: "Of course! How can I assist you today?",
    audio_url: "/audio/msg-2",
    image_url: null,
    created_at: oneHourAgo,
  },
  {
    id: "msg-3",
    role: "user",
    content: "Check this image",
    audio_url: null,
    image_url: "/images/user-upload.jpg",
    created_at: thirtyMinAgo,
  },
  {
    id: "msg-4",
    role: "assistant",
    content: LONG_MESSAGE,
    audio_url: null,
    image_url: null,
    created_at: tenMinAgo,
  },
  {
    id: "msg-5",
    role: "assistant",
    content: "Here is the image result.",
    audio_url: null,
    image_url: "/images/result.png",
    created_at: fiveMinAgo,
  },
];

export const MOCK_MESSAGES_EMPTY: ChatMessage[] = [];

export const MOCK_MESSAGES_WITH_THINKING = {
  messages: MOCK_MESSAGES,
  is_thinking: true,
};

// ---------------------------------------------------------------------------
// Failed message for retry testing
// ---------------------------------------------------------------------------

export const MOCK_FAILED_MESSAGE: ChatMessage = {
  id: "msg-failed",
  role: "user",
  content: "This message failed to send",
  audio_url: null,
  image_url: null,
  created_at: fiveMinAgo,
};

// ---------------------------------------------------------------------------
// Agent Sessions
// ---------------------------------------------------------------------------

export const MOCK_SESSIONS: AgentSession[] = [
  {
    id: "imessage/+1234567890",
    type: "contact",
    name: "Alice Johnson",
    tier: "admin",
    source: "imessage",
    chat_type: "individual",
    participants: ["+1234567890"],
    last_message: "Sure, I will handle that.",
    last_message_time: fiveMinAgo,
    last_message_is_from_me: false,
    status: "active",
  },
  {
    id: "signal/+0987654321",
    type: "contact",
    name: "Bob Smith",
    tier: "family",
    source: "signal",
    chat_type: "individual",
    participants: ["+0987654321"],
    last_message: "Thanks for the update!",
    last_message_time: tenMinAgo,
    last_message_is_from_me: true,
    status: "idle",
  },
  {
    id: "dispatch-app/test-uuid",
    type: "dispatch-api",
    name: "My Test Agent",
    tier: "admin",
    source: "dispatch-api",
    chat_type: "individual",
    participants: null,
    last_message: "Task completed successfully.",
    last_message_time: thirtyMinAgo,
    last_message_is_from_me: false,
    status: "active",
  },
  {
    id: "discord/test-channel",
    type: "contact",
    name: "Discord Bot Channel",
    tier: "favorite",
    source: "discord",
    chat_type: "group",
    participants: null,
    last_message: "Bot response received.",
    last_message_time: oneHourAgo,
    last_message_is_from_me: false,
    status: "error",
  },
];

export const MOCK_NEW_SESSION = {
  id: "dispatch-app/new-agent",
  name: "New Agent Session",
  status: "active",
};

// ---------------------------------------------------------------------------
// Agent Messages (for dispatch-app/test-uuid)
// ---------------------------------------------------------------------------

export const MOCK_AGENT_MESSAGES: AgentMessage[] = [
  {
    id: "amsg-1",
    role: "user",
    text: "Run the deployment script",
    sender: "admin",
    is_from_me: true,
    timestamp_ms: new Date(twoHoursAgo).getTime(),
    source: "dispatch-api",
    has_attachment: false,
  },
  {
    id: "amsg-2",
    role: "assistant",
    text: "Deployment completed. All services are running.",
    sender: "agent",
    is_from_me: false,
    timestamp_ms: new Date(oneHourAgo).getTime(),
    source: "dispatch-api",
    has_attachment: false,
  },
  {
    id: "amsg-3",
    role: "user",
    text: "Check the logs for errors",
    sender: "admin",
    is_from_me: true,
    timestamp_ms: new Date(thirtyMinAgo).getTime(),
    source: "dispatch-api",
    has_attachment: false,
  },
  {
    id: "amsg-4",
    role: "assistant",
    text: "No errors found in the last 24 hours. System is healthy.",
    sender: "agent",
    is_from_me: false,
    timestamp_ms: new Date(fiveMinAgo).getTime(),
    source: "dispatch-api",
    has_attachment: false,
  },
];

// ---------------------------------------------------------------------------
// SDK Events
// ---------------------------------------------------------------------------

export const MOCK_SDK_EVENTS: SdkEvent[] = [
  {
    id: 1,
    timestamp: new Date(thirtyMinAgo).getTime(),
    session_name: "dispatch-app/test-uuid",
    chat_id: "test-uuid",
    event_type: "tool_use",
    tool_name: "Bash",
    tool_use_id: "tu-1",
    duration_ms: null,
    is_error: false,
    payload: "ls -la /var/log",
    num_turns: 1,
  },
  {
    id: 2,
    timestamp: new Date(thirtyMinAgo).getTime() + 1500,
    session_name: "dispatch-app/test-uuid",
    chat_id: "test-uuid",
    event_type: "tool_result",
    tool_name: "Bash",
    tool_use_id: "tu-1",
    duration_ms: 1500,
    is_error: false,
    payload: "total 48\ndrwxr-xr-x  12 root  wheel  384 Mar 22 10:00 .",
    num_turns: 1,
  },
  {
    id: 3,
    timestamp: new Date(tenMinAgo).getTime(),
    session_name: "dispatch-app/test-uuid",
    chat_id: "test-uuid",
    event_type: "tool_use",
    tool_name: "Read",
    tool_use_id: "tu-2",
    duration_ms: null,
    is_error: false,
    payload: "/etc/hosts",
    num_turns: 2,
  },
  {
    id: 4,
    timestamp: new Date(tenMinAgo).getTime() + 200,
    session_name: "dispatch-app/test-uuid",
    chat_id: "test-uuid",
    event_type: "tool_result",
    tool_name: "Read",
    tool_use_id: "tu-2",
    duration_ms: 200,
    is_error: false,
    payload: "127.0.0.1 localhost",
    num_turns: 2,
  },
  {
    id: 5,
    timestamp: new Date(fiveMinAgo).getTime(),
    session_name: "dispatch-app/test-uuid",
    chat_id: "test-uuid",
    event_type: "result",
    tool_name: null,
    tool_use_id: null,
    duration_ms: null,
    is_error: false,
    payload: null,
    num_turns: 3,
  },
  {
    id: 6,
    timestamp: new Date(fiveMinAgo).getTime() + 100,
    session_name: "dispatch-app/test-uuid",
    chat_id: "test-uuid",
    event_type: "tool_use",
    tool_name: "Write",
    tool_use_id: "tu-3",
    duration_ms: null,
    is_error: true,
    payload: "Permission denied: /etc/readonly-file",
    num_turns: 3,
  },
];

// Long payload for expand/collapse testing
const LONG_PAYLOAD = "x".repeat(600);

export const MOCK_SDK_EVENTS_LONG_PAYLOAD: SdkEvent[] = [
  {
    id: 100,
    timestamp: Date.now(),
    session_name: "dispatch-app/test-uuid",
    chat_id: "test-uuid",
    event_type: "tool_use",
    tool_name: "Bash",
    tool_use_id: "tu-100",
    duration_ms: 3000,
    is_error: false,
    payload: LONG_PAYLOAD,
    num_turns: 1,
  },
];

// ---------------------------------------------------------------------------
// Logs
// ---------------------------------------------------------------------------

export const MOCK_LOG_LINES: string[] = [
  "2026-03-22 10:00:00 INFO  [manager] Starting dispatch manager...",
  "2026-03-22 10:00:01 INFO  [manager] Connected to database",
  "2026-03-22 10:00:02 WARNING  [manager] Signal daemon not running, retrying...",
  "2026-03-22 10:00:03 INFO  [manager] Signal daemon connected",
  "2026-03-22 10:00:04 ERROR  [manager] Failed to process message: timeout",
  "2026-03-22 10:00:05 INFO  [manager] Recovered from timeout",
  "2026-03-22 10:00:06 INFO  [manager] Processing chat message from +1234567890",
  "2026-03-22 10:00:07 WARNING  [manager] High memory usage detected: 85%",
  "2026-03-22 10:00:08 INFO  [manager] Message delivered successfully",
  "2026-03-22 10:00:09 ERROR  [manager] Traceback (most recent call last): ...",
];

export const MOCK_LOG_LINES_EMPTY: string[] = [];

// ---------------------------------------------------------------------------
// Error responses
// ---------------------------------------------------------------------------

export const MOCK_ERROR_RESPONSE = {
  status: 500,
  body: { error: "Internal Server Error" },
};

export const MOCK_NOT_FOUND_RESPONSE = {
  status: 404,
  body: { error: "Not Found" },
};
