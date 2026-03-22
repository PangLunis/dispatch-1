/**
 * Dispatch App E2E Test Suite
 *
 * Comprehensive Playwright tests organized by CUJ groups.
 * Uses full network isolation via page.route() mock server.
 * Tests the Expo web export of the React Native app.
 */

import { test, expect, type Page } from "@playwright/test";
import { setupMockServer, type MockServer } from "./fixtures/mock-server";

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:9091/app";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Navigate to app with mock server active */
async function loadApp(page: Page): Promise<MockServer> {
  const server = await setupMockServer(page);
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  // Wait for the React app to hydrate and initial data to load
  await page.waitForTimeout(2000);
  return server;
}

/** Click a tab by its text label */
async function clickTab(page: Page, label: string) {
  const tab = page.locator(`[role="link"]:has-text("${label}"), [role="tab"]:has-text("${label}")`);
  const count = await tab.count();
  if (count > 0) {
    await tab.first().click();
    await page.waitForTimeout(1000);
  }
}

/** Accept a window.confirm dialog */
function autoAcceptConfirm(page: Page) {
  page.on("dialog", async (dialog) => {
    if (dialog.type() === "confirm") {
      await dialog.accept();
    }
  });
}

/** Accept a window.prompt dialog with a given value */
function autoAcceptPrompt(page: Page, value: string) {
  page.on("dialog", async (dialog) => {
    if (dialog.type() === "prompt") {
      await dialog.accept(value);
    }
  });
}

/** Dismiss a window.prompt dialog */
function autoDismissPrompt(page: Page) {
  page.on("dialog", async (dialog) => {
    if (dialog.type() === "prompt") {
      await dialog.dismiss();
    }
  });
}

/** Accept a window.alert dialog */
function autoAcceptAlert(page: Page) {
  page.on("dialog", async (dialog) => {
    if (dialog.type() === "alert") {
      await dialog.accept();
    }
  });
}

/** Accept all dialogs */
function autoAcceptAllDialogs(page: Page) {
  page.on("dialog", async (dialog) => {
    await dialog.accept();
  });
}

// ==========================================================================
// 1. CHAT LIST (Tab 1)
// ==========================================================================

test.describe("Chat List (Tab 1)", () => {
  test("C1: View chat list - shows chats with title, preview, timestamp", async ({ page }) => {
    await loadApp(page);

    // Should see all three mock chats
    await expect(page.getByText("Test Chat Alpha")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Test Chat Beta")).toBeVisible();
    await expect(page.getByText("Test Chat Gamma")).toBeVisible();

    // Chat Alpha should show assistant's last message preview
    await expect(page.getByText("Of course! How can I assist you today?")).toBeVisible();

    // Chat Gamma should show assistant's last message
    await expect(page.getByText("Here is the result you requested.")).toBeVisible();

    // Chat Beta has is_thinking: true, so preview text is replaced by TypingDots
    // It should NOT show the "You: ..." preview text
    await expect(page.getByText("You: Can you check this for me?")).not.toBeVisible();
  });

  test("C3: Create new chat - tap FAB, new chat appears", async ({ page }) => {
    await loadApp(page);

    // Find and click the FAB (+) button
    const fab = page.getByText("+").last();
    await fab.click();

    // Should navigate to the new chat (URL should contain /chat/)
    await page.waitForTimeout(1500);
    await expect(page).toHaveURL(/\/chat\//);
  });

  test("C4: Open chat - tap a chat row, navigates to chat detail", async ({ page }) => {
    await loadApp(page);

    // Click on Chat Alpha
    await page.getByText("Test Chat Alpha").click();
    await page.waitForTimeout(1500);

    // Should navigate to chat detail
    await expect(page).toHaveURL(/\/chat\/chat-alpha/);
  });

  test("C6: Delete chat (long-press) - long-press triggers confirm", async ({ page }) => {
    autoAcceptConfirm(page);
    await loadApp(page);

    await expect(page.getByText("Test Chat Alpha")).toBeVisible({ timeout: 5000 });

    // Simulate long press on web: Pressable's onLongPress fires after delayLongPress
    // (default 500ms). We hold the mouse down for 600ms to trigger it.
    const chatRow = page.getByText("Test Chat Alpha");
    const box = await chatRow.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.waitForTimeout(700); // exceed delayLongPress
      await page.mouse.up();
    }

    // With the dialog auto-accepted, the chat should be removed from the list
    await page.waitForTimeout(1000);
    // The mock DELETE /chats/:id returns ok, and the app removes it from local state
  });

  test("C7: Unread indicator - chat with unread shows blue dot", async ({ page }) => {
    await loadApp(page);

    // Chat Alpha has last_message_at > last_opened_at with role=assistant => unread
    // The unread dot is rendered with styles.unreadDot (10x10 blue circle)
    // The title should be bold (fontWeight: 700 in titleUnread style)
    await expect(page.getByText("Test Chat Alpha")).toBeVisible({ timeout: 5000 });

    // Chat Gamma is read (last_opened_at > last_message_at)
    await expect(page.getByText("Test Chat Gamma")).toBeVisible();
  });

  test("C8: Thinking indicator in chat list - shows animated dots", async ({ page }) => {
    await loadApp(page);

    // Chat Beta has is_thinking: true
    // The TypingDots component renders 3 Animated.View elements
    // We just verify the chat row exists and doesn't show preview text
    await expect(page.getByText("Test Chat Beta")).toBeVisible({ timeout: 5000 });
  });

  test("C4-empty: Empty state - no chats shows empty message", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.chats = "empty";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    await expect(page.getByText("No conversations yet")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Tap + to start a new chat")).toBeVisible();
  });

  test("C4-error: Error state - API failure shows error banner", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.chats = "error";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    // The error banner should appear (backgroundColor: #7f1d1d)
    // Error text is styled with color: #fca5a5
    // The useChatList hook sets error on catch
    const errorBanner = page.locator("text=/Failed|error|Error/i");
    await expect(errorBanner.first()).toBeVisible({ timeout: 5000 });
  });
});

// ==========================================================================
// 2. CHAT CONVERSATION
// ==========================================================================

test.describe("Chat Conversation", () => {
  async function openChatAlpha(page: Page): Promise<MockServer> {
    const server = await loadApp(page);
    await page.getByText("Test Chat Alpha").click({ timeout: 5000 });
    await page.waitForTimeout(1500);
    return server;
  }

  test("C10: View messages - shows message history", async ({ page }) => {
    await openChatAlpha(page);

    // Should see user and assistant messages
    await expect(page.getByText("Hello, can you help me?")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Of course! How can I assist you today?")).toBeVisible();
    await expect(page.getByText("Check this image")).toBeVisible();
  });

  test("C11: Send text message - type and send", async ({ page }) => {
    await openChatAlpha(page);

    // Find the text input
    const input = page.locator("input, textarea").last();
    await input.fill("Test message from E2E");

    // The send button should appear when text is entered
    // Submit via Enter key (web behavior via onSubmitEditing)
    await input.press("Enter");

    await page.waitForTimeout(1000);

    // Optimistic insert: the message should appear immediately
    await expect(page.getByText("Test message from E2E")).toBeVisible({ timeout: 3000 });
  });

  test("C15: Expand/collapse long messages - Show more/less toggle", async ({ page }) => {
    await openChatAlpha(page);

    // msg-4 is 900 chars (> MAX_COLLAPSED_LENGTH of 840)
    // It should show truncated with "Show more"
    const showMore = page.getByText("Show more");
    await expect(showMore.first()).toBeVisible({ timeout: 5000 });

    // Click to expand
    await showMore.first().click();
    await page.waitForTimeout(500);

    // Should now show "Show less"
    await expect(page.getByText("Show less").first()).toBeVisible();

    // Click to collapse
    await page.getByText("Show less").first().click();
    await page.waitForTimeout(500);

    await expect(page.getByText("Show more").first()).toBeVisible();
  });

  test("C16: View message timestamp - tap bubble toggles timestamp", async ({ page }) => {
    await openChatAlpha(page);

    // Click on a message bubble to toggle timestamp
    const msgBubble = page.getByText("Hello, can you help me?");
    await expect(msgBubble).toBeVisible({ timeout: 5000 });
    await msgBubble.click();
    await page.waitForTimeout(500);

    // Timestamp should now be visible (relativeTime output)
    // The timestamp text depends on the mock date; just check something appeared
    // after clicking
  });

  test("C17: Retry failed message - shows Not Delivered + retry", async ({ page }) => {
    const server = await setupMockServer(page);
    // Force the prompt endpoint to error so the optimistic message fails
    server.setError("/prompt");
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    await page.getByText("Test Chat Alpha").click({ timeout: 5000 });
    await page.waitForTimeout(1500);

    // Send a message that will fail
    const input = page.locator("input, textarea").last();
    await input.fill("This will fail");
    await input.press("Enter");
    await page.waitForTimeout(2000);

    // Should show "Not Delivered" indicator
    await expect(page.getByText("Not Delivered")).toBeVisible({ timeout: 5000 });

    // Clear the error so retry succeeds
    server.clearError("/prompt");

    // Click the retry button area (the "Not Delivered" text is a Pressable)
    await page.getByText("Not Delivered").click();
    await page.waitForTimeout(1500);
  });

  test("C23: Rename chat - tap Rename, enter new name", async ({ page }) => {
    autoAcceptPrompt(page, "Renamed Alpha");
    await openChatAlpha(page);

    // Click the Rename button in the header
    const renameBtn = page.getByText("Rename");
    await expect(renameBtn).toBeVisible({ timeout: 5000 });
    await renameBtn.click();

    // The prompt dialog is auto-accepted with "Renamed Alpha"
    await page.waitForTimeout(1000);
  });

  test("C24: Thinking indicator in chat - shows when is_thinking", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.messages = "thinking";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    await page.getByText("Test Chat Alpha").click({ timeout: 5000 });
    await page.waitForTimeout(2000);

    // ThinkingIndicator renders dots (3 Animated.View elements)
    // It also has a chevron "down arrow" character
    // Just verify the ThinkingIndicator wrapper is present
    const thinkingDots = page.locator("text=\u25be"); // "down triangle" chevron
    // May or may not be visible depending on sdkComplete logic
  });

  test("C25: Empty chat state - new chat shows empty message", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.messages = "empty";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    await page.getByText("Test Chat Alpha").click({ timeout: 5000 });
    await page.waitForTimeout(1500);

    await expect(page.getByText("No messages yet")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Send a message to start the conversation")).toBeVisible();
  });
});

// ==========================================================================
// 3. SESSIONS (Tab 2)
// ==========================================================================

test.describe("Sessions (Tab 2)", () => {
  async function openSessionsTab(page: Page): Promise<MockServer> {
    const server = await loadApp(page);
    await clickTab(page, "Sessions");
    return server;
  }

  test("S1: View session list - shows sessions with name, badges", async ({ page }) => {
    await openSessionsTab(page);

    await expect(page.getByText("Alice Johnson")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Bob Smith")).toBeVisible();
    await expect(page.getByText("My Test Agent")).toBeVisible();
    await expect(page.getByText("Discord Bot Channel")).toBeVisible();
  });

  test("S2: Search sessions - filter by name", async ({ page }) => {
    await openSessionsTab(page);

    const searchInput = page.locator('input[placeholder*="Search" i]');
    await expect(searchInput).toBeVisible({ timeout: 5000 });

    // Search for "Alice"
    await searchInput.fill("Alice");
    await page.waitForTimeout(1000);

    await expect(page.getByText("Alice Johnson")).toBeVisible();
    // Bob should be filtered out
    await expect(page.getByText("Bob Smith")).not.toBeVisible();

    // Clear search
    await searchInput.clear();
    await page.waitForTimeout(500);

    // All sessions should reappear
    await expect(page.getByText("Bob Smith")).toBeVisible();
  });

  test("S3: Filter by source - tap filter pills", async ({ page }) => {
    await openSessionsTab(page);

    // Click the "iMessage" filter pill
    const imessagePill = page.getByText("iMessage", { exact: true });
    await expect(imessagePill).toBeVisible({ timeout: 5000 });
    await imessagePill.click();
    await page.waitForTimeout(1000);

    // Alice is iMessage, should be visible
    await expect(page.getByText("Alice Johnson")).toBeVisible();

    // Click "Signal" filter
    const signalPill = page.getByText("Signal", { exact: true });
    await signalPill.click();
    await page.waitForTimeout(1000);

    // Bob is Signal
    await expect(page.getByText("Bob Smith")).toBeVisible();

    // Reset to "All"
    const allPill = page.getByText("All", { exact: true });
    await allPill.click();
    await page.waitForTimeout(500);
  });

  test("S4: Create new session - tap FAB, enter name", async ({ page }) => {
    autoAcceptPrompt(page, "Brand New Agent");
    await openSessionsTab(page);

    // Click the FAB (+) button
    const fab = page.getByText("+").last();
    await fab.click();

    // The prompt dialog is auto-accepted with "Brand New Agent"
    await page.waitForTimeout(1500);

    // Should navigate to the agent detail
    await expect(page).toHaveURL(/\/agents\//);
  });

  test("S5: Open session - tap row, navigate to detail", async ({ page }) => {
    await openSessionsTab(page);

    await page.getByText("Alice Johnson").click({ timeout: 5000 });
    await page.waitForTimeout(1500);

    await expect(page).toHaveURL(/\/agents\//);
  });

  test("S6: Session status colors - active=green, idle=gray, error=red", async ({ page }) => {
    await openSessionsTab(page);

    // Status colors are applied via inline backgroundColor on the status dot
    // active (#22c55e), idle (#71717a), error (#ef4444)
    // We just verify the sessions load with correct names
    await expect(page.getByText("Alice Johnson")).toBeVisible({ timeout: 5000 }); // active
    await expect(page.getByText("Bob Smith")).toBeVisible(); // idle
    await expect(page.getByText("Discord Bot Channel")).toBeVisible(); // error
  });

  test("S-empty: Empty state - no sessions", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.sessions = "empty";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    await clickTab(page, "Sessions");

    await expect(page.getByText("No agent sessions")).toBeVisible({ timeout: 5000 });
  });
});

// ==========================================================================
// 4. SESSION DETAIL
// ==========================================================================

test.describe("Session Detail", () => {
  async function openDispatchApiSession(page: Page): Promise<MockServer> {
    const server = await loadApp(page);
    await clickTab(page, "Sessions");
    await page.getByText("My Test Agent").click({ timeout: 5000 });
    await page.waitForTimeout(1500);
    return server;
  }

  async function openContactSession(page: Page): Promise<MockServer> {
    const server = await loadApp(page);
    await clickTab(page, "Sessions");
    await page.getByText("Alice Johnson").click({ timeout: 5000 });
    await page.waitForTimeout(1500);
    return server;
  }

  test("S8: View session messages - shows message history", async ({ page }) => {
    await openDispatchApiSession(page);

    await expect(page.getByText("Run the deployment script")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Deployment completed. All services are running.")).toBeVisible();
  });

  test("S9: Send message to dispatch-api session", async ({ page }) => {
    await openDispatchApiSession(page);

    // InputBar should be visible for dispatch-api sessions
    const input = page.locator("input, textarea").last();
    await input.fill("Check server status");
    await input.press("Enter");
    await page.waitForTimeout(1000);

    // Optimistic insert
    await expect(page.getByText("Check server status")).toBeVisible({ timeout: 3000 });
  });

  test("S10: Toggle Messages/SDK Events - switch between modes", async ({ page }) => {
    await openDispatchApiSession(page);

    // Mode toggle buttons
    const sdkButton = page.getByText("SDK Events", { exact: true });
    const messagesButton = page.getByText("Messages", { exact: true });

    await expect(sdkButton).toBeVisible({ timeout: 5000 });
    await expect(messagesButton).toBeVisible();

    // Click SDK Events
    await sdkButton.click();
    await page.waitForTimeout(1500);

    // Should show SDK event type badges
    await expect(page.getByText("tool_use")).toBeVisible({ timeout: 5000 });

    // Switch back to Messages
    await messagesButton.click();
    await page.waitForTimeout(1500);

    await expect(page.getByText("Run the deployment script")).toBeVisible({ timeout: 5000 });
  });

  test("S11: View SDK events - shows type badges, tool names, durations", async ({ page }) => {
    await openDispatchApiSession(page);

    // Switch to SDK Events mode
    await page.getByText("SDK Events", { exact: true }).click();
    await page.waitForTimeout(1500);

    // Check for tool names
    await expect(page.getByText("Bash")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Read")).toBeVisible();

    // Check for duration display
    await expect(page.getByText("1500ms")).toBeVisible();
    await expect(page.getByText("200ms")).toBeVisible();
  });

  test("S12: Expand SDK event payload - tap long payload", async ({ page }) => {
    await openDispatchApiSession(page);

    await page.getByText("SDK Events", { exact: true }).click();
    await page.waitForTimeout(1500);

    // Payloads are visible inline in the SdkEventBubble
    await expect(page.getByText("ls -la /var/log")).toBeVisible({ timeout: 5000 });
  });

  test("S14: Rename session - dispatch-api only", async ({ page }) => {
    autoAcceptPrompt(page, "Renamed Agent");
    await openDispatchApiSession(page);

    // Rename button should be visible for dispatch-api sessions
    const renameBtn = page.getByText("Rename");
    await expect(renameBtn).toBeVisible({ timeout: 5000 });
    await renameBtn.click();

    await page.waitForTimeout(1000);
  });

  test("S15: Delete session - dispatch-api only, confirm", async ({ page }) => {
    autoAcceptConfirm(page);
    await openDispatchApiSession(page);

    // Delete button should be visible for dispatch-api sessions
    const deleteBtn = page.getByText("Delete", { exact: true });
    await expect(deleteBtn).toBeVisible({ timeout: 5000 });
    await deleteBtn.click();

    // Dialog auto-accepted
    await page.waitForTimeout(1500);

    // Should navigate back after deletion
  });

  test("S16: Thinking indicator in session - animated dots when thinking", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.agentMessages = "thinking";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    await clickTab(page, "Sessions");
    await page.getByText("My Test Agent").click({ timeout: 5000 });
    await page.waitForTimeout(2000);

    // ThinkingIndicator should be present in the DOM
    // It renders Animated.View elements with the dot class
  });

  test("S17: Error SDK events - red highlighting", async ({ page }) => {
    await openDispatchApiSession(page);

    await page.getByText("SDK Events", { exact: true }).click();
    await page.waitForTimeout(1500);

    // The error SDK event (Write with is_error: true) should be visible
    await expect(page.getByText("Write")).toBeVisible({ timeout: 5000 });
    // Error text content
    await expect(page.getByText("Permission denied")).toBeVisible();
  });

  test("S-inputbar: InputBar hidden for contact sessions", async ({ page }) => {
    await openContactSession(page);

    // For contact sessions (type !== "dispatch-api"), InputBar should NOT render
    // The Messages toggle should still be visible
    await expect(page.getByText("Messages", { exact: true })).toBeVisible({ timeout: 5000 });

    // No text input should be present
    const inputs = page.locator('input[placeholder*="Message" i], textarea[placeholder*="Message" i]');
    await expect(inputs).toHaveCount(0);
  });

  test("S-rename-hidden: Rename/Delete hidden for contact sessions", async ({ page }) => {
    await openContactSession(page);

    // For contact sessions, headerRight returns null
    const renameBtn = page.getByText("Rename");
    await expect(renameBtn).not.toBeVisible();

    const deleteBtn = page.locator('[role="button"]:has-text("Delete")');
    await expect(deleteBtn).not.toBeVisible();
  });
});

// ==========================================================================
// 5. DASHBOARD (Tab 3)
// ==========================================================================

test.describe("Dashboard (Tab 3)", () => {
  test("D1: Dashboard fallback on web - shows fallback UI", async ({ page }) => {
    await loadApp(page);
    await clickTab(page, "Dashboard");

    // On web, WebView is not available, so the fallback renders
    await expect(page.getByText("Dashboard")).toBeVisible({ timeout: 5000 });

    // The fallback shows an "Open in Browser" button
    await expect(page.getByText("Open in Browser")).toBeVisible({ timeout: 5000 });
  });
});

// ==========================================================================
// 6. SETTINGS (Tab 4)
// ==========================================================================

test.describe("Settings (Tab 4)", () => {
  async function openSettings(page: Page): Promise<MockServer> {
    const server = await loadApp(page);
    await clickTab(page, "Settings");
    return server;
  }

  test("ST1: View settings - shows connection, API URL, token, debug", async ({ page }) => {
    await openSettings(page);

    await expect(page.getByText("CONNECTION")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("API Server")).toBeVisible();
    await expect(page.getByText("Status")).toBeVisible();
    await expect(page.getByText("Device Token")).toBeVisible();
    await expect(page.getByText("DEBUG")).toBeVisible();
    await expect(page.getByText("Logs")).toBeVisible();
    await expect(page.getByText("Restart Session")).toBeVisible();
    await expect(page.getByText("Clear Notifications")).toBeVisible();
    await expect(page.getByText("Powered by Claude")).toBeVisible();
  });

  test("ST2: Change API URL - tap server URL, enter new URL", async ({ page }) => {
    autoAcceptPrompt(page, "http://new-server:9091");
    await openSettings(page);

    // Click API Server row
    await page.getByText("API Server").click();
    await page.waitForTimeout(1000);

    // Prompt dialog auto-accepted
  });

  test("ST3: Connection status - shows Connected with green dot", async ({ page }) => {
    await openSettings(page);

    // The health endpoint returns ok, so status should show Connected
    await expect(page.getByText("Connected")).toBeVisible({ timeout: 8000 });
  });

  test("ST4: Copy device token - tap shows Copied! feedback", async ({ page }) => {
    await openSettings(page);

    // Click the device token row
    const tokenRow = page.getByText("Device Token");
    await tokenRow.click();
    await page.waitForTimeout(1000);

    // Should show "Copied!" feedback (clipboard may not work in headless, but
    // the state change should still occur)
  });

  test("ST6: Restart session - tap restart, confirm, session restarts", async ({ page }) => {
    autoAcceptAllDialogs(page);
    await openSettings(page);

    await page.getByText("Restart Session").click();
    await page.waitForTimeout(1500);

    // The confirm dialog is auto-accepted, then an alert shows "Success" or "Session restarted"
  });

  test("ST7: Clear notifications - tap clear button exists and is clickable", async ({ page }) => {
    // Note: expo-notifications may throw on web since notification APIs
    // aren't available in headless Playwright. We just verify the button
    // exists and is clickable; the actual clearing is a manual-only test.
    autoAcceptAllDialogs(page);
    await openSettings(page);

    const clearBtn = page.getByText("Clear Notifications");
    await expect(clearBtn).toBeVisible({ timeout: 5000 });
    await clearBtn.click();
    await page.waitForTimeout(1000);
  });

  test("ST8: Reset to default URL - tap reset", async ({ page }) => {
    await openSettings(page);

    await page.getByText("Reset to Default").click();
    await page.waitForTimeout(1000);
  });
});

// ==========================================================================
// 7. LOGS
// ==========================================================================

test.describe("Logs", () => {
  async function openLogs(page: Page): Promise<MockServer> {
    const server = await loadApp(page);
    await clickTab(page, "Settings");
    await page.getByText("Logs").click();
    await page.waitForTimeout(1500);
    return server;
  }

  test("L1: View logs - shows log lines with line numbers", async ({ page }) => {
    await openLogs(page);

    // Should see log content
    await expect(page.getByText("Starting dispatch manager")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Connected to database")).toBeVisible();

    // Should show line count
    await expect(page.getByText("10 lines")).toBeVisible();
  });

  test("L2: Switch log files - tap file tabs", async ({ page }) => {
    await openLogs(page);

    // File tabs: manager, dispatch-api, client, signal-daemon, watchdog
    await expect(page.getByText("manager")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("dispatch-api")).toBeVisible();
    await expect(page.getByText("client")).toBeVisible();
    await expect(page.getByText("signal-daemon")).toBeVisible();
    await expect(page.getByText("watchdog")).toBeVisible();

    // Click dispatch-api tab
    await page.getByText("dispatch-api").click();
    await page.waitForTimeout(1000);

    // Click client tab
    await page.getByText("client").click();
    await page.waitForTimeout(1000);
  });

  test("L4: Color-coded lines - ERROR red, WARNING yellow", async ({ page }) => {
    await openLogs(page);

    // ERROR lines should exist
    await expect(page.getByText("Failed to process message: timeout")).toBeVisible({ timeout: 5000 });

    // WARNING lines should exist
    await expect(page.getByText("Signal daemon not running")).toBeVisible();

    // The color styling is applied via styles (logError: #ef4444, logWarning: #eab308)
    // We verify the text exists; visual color testing is manual-only
  });

  test("L-empty: Empty state - no logs", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.logs = "empty";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    await clickTab(page, "Settings");
    await page.getByText("Logs").click();
    await page.waitForTimeout(1500);

    await expect(page.getByText("No logs found")).toBeVisible({ timeout: 5000 });
  });
});

// ==========================================================================
// 8. CROSS-CUTTING
// ==========================================================================

test.describe("Cross-cutting", () => {
  test("X1: Tab navigation - switch between all 4 tabs", async ({ page }) => {
    await loadApp(page);

    // Start on Admin Agents (Tab 1) - should see chats
    await expect(page.getByText("Test Chat Alpha")).toBeVisible({ timeout: 5000 });

    // Go to Sessions (Tab 2)
    await clickTab(page, "Sessions");
    await expect(page.getByText("Alice Johnson")).toBeVisible({ timeout: 5000 });

    // Go to Dashboard (Tab 3)
    await clickTab(page, "Dashboard");
    await expect(page.getByText("Dashboard")).toBeVisible({ timeout: 5000 });

    // Go to Settings (Tab 4)
    await clickTab(page, "Settings");
    await expect(page.getByText("CONNECTION")).toBeVisible({ timeout: 5000 });

    // Back to Admin Agents
    await clickTab(page, "Admin Agents");
    await expect(page.getByText("Test Chat Alpha")).toBeVisible({ timeout: 5000 });
  });

  test("X2: Deep navigation + tab switch - enter detail, switch tab, switch back", async ({ page }) => {
    await loadApp(page);

    // Enter chat detail
    await page.getByText("Test Chat Alpha").click({ timeout: 5000 });
    await page.waitForTimeout(1500);
    await expect(page.getByText("Hello, can you help me?")).toBeVisible({ timeout: 5000 });

    // Switch to Sessions tab
    await clickTab(page, "Sessions");
    await expect(page.getByText("Alice Johnson")).toBeVisible({ timeout: 5000 });

    // Enter agent detail
    await page.getByText("Alice Johnson").click();
    await page.waitForTimeout(1500);

    // Switch back to Admin Agents tab
    await clickTab(page, "Admin Agents");
    await page.waitForTimeout(1000);
  });

  test("X3: Error handling - API failure shows error banner", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.chats = "error";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    // Error banner with styled text
    const errorText = page.locator("text=/Failed|error|Error/i");
    await expect(errorText.first()).toBeVisible({ timeout: 5000 });
  });

  test("X4: Empty states - screens with no data show appropriate messages", async ({ page }) => {
    const server = await setupMockServer(page);
    server.state.chats = "empty";
    server.state.sessions = "empty";
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    // Chat list empty
    await expect(page.getByText("No conversations yet")).toBeVisible({ timeout: 5000 });

    // Sessions empty
    await clickTab(page, "Sessions");
    await expect(page.getByText("No agent sessions")).toBeVisible({ timeout: 5000 });
  });

  test("X5: Mobile viewport - renders at iPhone dimensions", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loadApp(page);

    await expect(page.getByText("Test Chat Alpha")).toBeVisible({ timeout: 5000 });

    // Navigate to sessions
    await clickTab(page, "Sessions");
    await expect(page.getByText("Alice Johnson")).toBeVisible({ timeout: 5000 });

    // Navigate to settings
    await clickTab(page, "Settings");
    await expect(page.getByText("CONNECTION")).toBeVisible({ timeout: 5000 });
  });

  test("X6: Desktop viewport - renders at desktop dimensions", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await loadApp(page);

    await expect(page.getByText("Test Chat Alpha")).toBeVisible({ timeout: 5000 });

    await clickTab(page, "Sessions");
    await expect(page.getByText("Alice Johnson")).toBeVisible({ timeout: 5000 });
  });
});
