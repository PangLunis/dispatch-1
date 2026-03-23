import type { AgentSession } from "../api/types";

/**
 * Prompt injected when user selects a session from the Sessions picker.
 * Claude reads the session's transcript and summarizes context so work can continue here.
 */
export function SESSION_CONTEXT_PROMPT(session: AgentSession): string {
  // Derive backend from source (imessage, signal, discord, dispatch-app, sven-app → use as-is)
  const backend = session.source;
  // Sanitize ID for filesystem paths (+ → _ to match transcript dir convention)
  const sanitizedId = session.id.replace(/\+/g, "_");

  return `Pull context from ${session.name}'s ${session.source} session so we can continue their work here.

Run this command to read recent activity:
\`uv run ~/.claude/skills/sms-assistant/scripts/read_transcript.py --session ${backend}/${sanitizedId} --limit 30\`

If that returns an error, empty output, or only metadata — fall back to reading files directly from ~/transcripts/${backend}/${sanitizedId}/. Find the newest file by modification time, and read the last 200 lines.

Chat ID: ${session.id}

Present a concise summary (3-8 bullets, plain language) covering:
1. What was being worked on (include rough timeframe)
2. Current status
3. Pending actions or open questions
4. Key decisions made and their rationale

Error handling:
- If the session directory doesn't exist, say so and ask what to do.
- If the transcript is empty or only contains system messages, report "no meaningful activity found."
- Never fabricate or assume content.

RULES: READ-ONLY context pull. No side effects. After summarizing, ask what to do.`;
}

/**
 * Prompt injected when user taps the Review button.
 * Triggers subagent-review skill to review and iterate to 9.0.
 */
export const REVIEW_PROMPT =
  "Use /subagent-review to review the above. Iterate until you reach 9.0. Do not stop before 9.0.";

/**
 * Prompt injected when user taps the Plan/Build/Test button.
 * Triggers a full autonomous implementation loop with review gates.
 */
export const PLAN_BUILD_TEST_PROMPT = `Plan, build, and test the implementation discussed above.

1. PLAN: First, restate your understanding of the task. Web search to ground yourself in canonical approaches. Write a detailed plan. Share it with me, then review with /subagent-review. You must reach 9.0. Do not stop before 9.0. If you've already planned this in the conversation above and reached 9.0, skip to BUILD.

2. BUILD: Implement step by step. After each major step, review the code against the plan with /subagent-review. You must reach 9.0 on each step. Do not stop before 9.0. If /subagent-review is unavailable, self-review against the plan and proceed.

3. TEST: Use /manual-test to test the result. Fix any issues found. You must reach 9.0. Do not stop before 9.0.

4. DELIVER: Summarize what was built, what was tested, and any known limitations or next steps.

If you hit a blocker, revise the plan to work around it. If the approach is unviable, explain why and propose an alternative. Do not skip steps.

Keep going until done. Do not stop or ask for input unless you absolutely must have clarification to proceed. Make decisions, solve problems, and push through to completion autonomously.`;
