import type { SdkEvent } from "../api/types";

/**
 * Map SDK tool names to human-readable descriptions.
 */
const TOOL_LABELS: Record<string, string> = {
  Bash: "Running command",
  Read: "Reading file",
  Write: "Writing file",
  Edit: "Editing file",
  Grep: "Searching code",
  Glob: "Finding files",
  Agent: "Running subagent",
  WebSearch: "Searching the web",
  WebFetch: "Fetching webpage",
  Skill: "Using skill",
  NotebookEdit: "Editing notebook",
};

/**
 * Map event types to human-readable status.
 */
const EVENT_LABELS: Record<string, string> = {
  tool_use: "Working",
  tool_result: "Done",
  result: "Finishing up",
  text: "Responding",
  error: "Error",
};

/**
 * Get a human-readable tool info string from the latest relevant SDK event.
 * Only shows actual tool activity (tool_use / tool_result), not filler like
 * "Finishing up" or "Responding". Returns undefined when there's nothing
 * meaningful to show — the ThinkingIndicator will just show dots.
 */
export function formatToolInfo(events: SdkEvent[]): string | undefined {
  if (events.length === 0) return undefined;

  // Walk backwards to find the most recent tool event
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];

    if (ev.tool_name) {
      const label = TOOL_LABELS[ev.tool_name] || ev.tool_name;
      if (ev.event_type === "tool_use") {
        return label;
      }
      if (ev.event_type === "tool_result") {
        return `${label} done`;
      }
    }

    if (ev.event_type === "error") {
      return "Error encountered";
    }
  }

  return undefined;
}

/**
 * Get the last assistant text from SDK events.
 * Looks for "text" event_type or "result" events that contain assistant text payload.
 */
export function getLastAssistantText(events: SdkEvent[]): string | undefined {
  if (events.length === 0) return undefined;

  // Walk backwards to find an event with a text payload
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev.event_type === "text" && ev.payload) {
      return ev.payload;
    }
    if (ev.event_type === "result" && ev.payload) {
      // Result payload might contain the assistant's final text
      try {
        const parsed = JSON.parse(ev.payload);
        if (parsed.text) return parsed.text;
      } catch {
        // Not JSON, use raw payload
        return ev.payload;
      }
    }
  }

  return undefined;
}
