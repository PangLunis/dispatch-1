import { createAgentSession, sendAgentMessage } from "../api/agents";

/** Max length for user-provided debug context to prevent prompt bloat */
const MAX_CONTEXT_LENGTH = 2000;

/** Timeout for session creation (ms) */
const CREATE_TIMEOUT = 15_000;

/** Chat IDs are UUIDs (with hyphens) or backend-prefixed UUIDs (e.g. dispatch-api:uuid) */
const CHAT_ID_PATTERN = /^[a-z0-9\-]+(?::[a-z0-9\-]+)?$/i;

/**
 * Race a promise against a timeout. Clears timer on resolution to avoid dangling callbacks.
 */
function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  let timerId: ReturnType<typeof setTimeout>;
  const timeout = new Promise<never>((_, reject) => {
    timerId = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([
    promise.finally(() => clearTimeout(timerId)),
    timeout,
  ]);
}

/**
 * Sanitize a string for safe interpolation into prompts.
 * Strips control chars and newlines to prevent prompt structure injection.
 */
function sanitizeForPrompt(text: string): string {
  return text.replace(/[\x00-\x1f\x7f]/g, " ").trim();
}

/**
 * Build a structured debug prompt with exact investigation paths.
 */
function buildDebugPrompt(chatId: string, chatTitle: string, context: string): string {
  const safeContext = sanitizeForPrompt(context).slice(0, MAX_CONTEXT_LENGTH);
  const safeTitle = sanitizeForPrompt(chatTitle);
  return [
    "You are a debug agent investigating an issue in a dispatch-app chat session.",
    "",
    "## Target Chat",
    `- Chat ID: ${chatId}`,
    `- Chat Title: ${safeTitle}`,
    `- Transcript path: ~/transcripts/dispatch-app/${chatId}/`,
    `- Backend: dispatch-app`,
    "",
    "## User's Bug Report",
    safeContext,
    "",
    "## Investigation Steps",
    `1. Read the chat transcript with: uv run ~/.claude/skills/sms-assistant/scripts/read_transcript.py --session dispatch-app/${chatId}`,
    `2. Check bus.db for recent events: sqlite3 ~/dispatch/state/bus.db "SELECT timestamp, event_type, tool_name, payload FROM sdk_events WHERE session_name LIKE '%${chatId}%' ORDER BY id DESC LIMIT 30"`,
    "3. Check daemon logs if relevant: tail -100 ~/dispatch/state/daemon.log",
    "4. Read relevant source code if the issue is in app behavior",
    "",
    "## Output Format",
    "Report your findings as a concise summary with:",
    "1. **Root cause** — what went wrong and why",
    "2. **Evidence** — the specific log lines, events, or code that confirm it",
    "3. **Proposed fix** — what should change to resolve it",
    "",
    "Do NOT apply changes automatically — propose the fix and wait for confirmation.",
  ].join("\n");
}

/** Result from startDebugSession */
export interface DebugSessionResult {
  id: string;
  name: string;
  /** Warning message if session was created but prompt send failed */
  warning?: string;
}

/**
 * Create an ephemeral debug agent session for a chat.
 *
 * Creates the session, sends the debug prompt, and returns session info
 * for navigation. The caller should navigate immediately.
 *
 * Note: This is an admin-only feature. The `context` parameter is user-supplied
 * free text interpolated into the agent prompt. This is a trusted input since
 * only admin-tier users can access the Debug Chat menu item.
 *
 * @throws On invalid chatId, session creation failure, or timeout.
 */
export async function startDebugSession(
  chatId: string,
  chatTitle: string,
  context: string,
): Promise<DebugSessionResult> {
  // Validate chat ID format — fail fast on invalid input
  if (!chatId || !CHAT_ID_PATTERN.test(chatId)) {
    throw new Error("Invalid chat ID format");
  }

  // Sanitize title for session name (strip special chars, limit length)
  const safeName = `Debug: ${chatTitle.replace(/[^\w\s\-().]/g, "").slice(0, 40)}`;

  // Create session with timeout to prevent indefinite disabled state
  const session = await withTimeout(
    createAgentSession(safeName),
    CREATE_TIMEOUT,
    "Session creation timed out — check Agent Sessions for a partial session",
  );

  if (!session?.id || !session?.name) {
    throw new Error("Session created but response was invalid");
  }

  // Build and send debug prompt — capture failure as warning with details
  const prompt = buildDebugPrompt(chatId, chatTitle, context);
  let warning: string | undefined;
  try {
    await sendAgentMessage(session.id, prompt);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "unknown error";
    warning = `Debug prompt failed to send (${detail}). You can re-enter your bug report in the session.`;
  }

  return { id: session.id, name: session.name, warning };
}
