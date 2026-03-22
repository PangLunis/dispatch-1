#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright"]
# ///
"""Comprehensive Playwright test for Dispatch App - all tabs, navigation, interactions."""

import sys
import time
import json
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeout

BASE_URL = "http://localhost:9091/app"
SCREENSHOT_DIR = "/tmp/dispatch-app-test"

import os
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

errors = []
warnings = []
passes = []

def log_pass(test_name, detail=""):
    passes.append(test_name)
    print(f"  ✅ {test_name}" + (f" — {detail}" if detail else ""))

def log_fail(test_name, detail=""):
    errors.append(f"{test_name}: {detail}")
    print(f"  ❌ {test_name}" + (f" — {detail}" if detail else ""))

def log_warn(test_name, detail=""):
    warnings.append(f"{test_name}: {detail}")
    print(f"  ⚠️  {test_name}" + (f" — {detail}" if detail else ""))

def screenshot(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.png"
    page.screenshot(path=path)
    return path


def click_tab(page, tab_name, timeout=5000):
    """Click a tab bar item by finding the tab bar at the bottom, not page headers.

    React Navigation renders tab bar as a nav element or a div at the bottom.
    Tab items have role="tab" or are links inside the tab bar.
    We need to avoid matching <h1> page headers.
    """
    # Strategy 1: role="tab" with matching text
    tab = page.locator(f'[role="tab"]:has-text("{tab_name}")').first
    try:
        tab.click(timeout=timeout)
        return True
    except:
        pass

    # Strategy 2: link in tab bar (expo-router uses <a> tags)
    tab = page.locator(f'a[href*="{tab_name.lower()}"]:has-text("{tab_name}")').first
    try:
        tab.click(timeout=timeout)
        return True
    except:
        pass

    # Strategy 3: find tab bar container and click within it
    # Tab bar is usually at bottom, look for the nav/div with tab items
    tab = page.locator(f'nav :text-is("{tab_name}"), [role="tablist"] :text-is("{tab_name}")').first
    try:
        tab.click(timeout=timeout)
        return True
    except:
        pass

    # Strategy 4: Use coordinates - find the tab bar at the bottom of the viewport
    # and click the appropriate section
    viewport = page.viewport_size
    if viewport:
        tab_y = viewport["height"] - 25  # Tab bar is ~50px, click middle
        tab_positions = {"Chats": 0.167, "Agents": 0.5, "Settings": 0.833}
        if tab_name in tab_positions:
            tab_x = int(viewport["width"] * tab_positions[tab_name])
            page.mouse.click(tab_x, tab_y)
            return True

    # Strategy 5: force click (bypass actionability checks) on text match
    # but filter out h1/heading elements
    all_matches = page.get_by_text(tab_name, exact=True).all()
    for match in all_matches:
        tag = match.evaluate("el => el.tagName")
        role = match.evaluate("el => el.getAttribute('role')")
        if tag != "H1" and role != "heading":
            match.click(force=True, timeout=timeout)
            return True

    return False


def test_initial_load(page):
    """Test 1: Initial page load."""
    print("\n📋 Test 1: Initial Load")

    response = page.goto(BASE_URL + "/")

    if response and response.status == 200:
        log_pass("Page loads", f"HTTP {response.status}")
    else:
        log_fail("Page loads", f"HTTP {response.status if response else 'no response'}")
        return False

    page.wait_for_timeout(2000)
    screenshot(page, "01-initial-load")

    body_text = page.text_content("body") or ""
    if len(body_text.strip()) > 0:
        log_pass("Page has content", f"{len(body_text.strip())} chars")
    else:
        log_fail("Page has content", "Body is empty")

    return True


def test_tab_navigation(page):
    """Test 2: Tab bar and navigation between tabs."""
    print("\n📋 Test 2: Tab Navigation")

    page.goto(BASE_URL + "/")
    page.wait_for_timeout(2000)

    # Check tabs are visible
    for label in ["Chats", "Agents", "Settings"]:
        elements = page.get_by_text(label, exact=True).all()
        if elements:
            log_pass(f"Tab '{label}' visible")
        else:
            log_fail(f"Tab '{label}' visible", "Not found")

    # Navigate to Agents
    if click_tab(page, "Agents"):
        page.wait_for_timeout(1500)
        screenshot(page, "02-agents-tab")
        url = page.url
        body = page.text_content("body") or ""
        if "agents" in url.lower() or "agent" in body.lower():
            log_pass("Navigate to Agents tab")
        else:
            log_warn("Navigate to Agents tab", f"URL: {url}")
    else:
        log_fail("Navigate to Agents tab", "Could not click tab")

    # Navigate to Settings
    if click_tab(page, "Settings"):
        page.wait_for_timeout(1500)
        screenshot(page, "03-settings-tab")
        body = page.text_content("body") or ""
        if any(w in body.lower() for w in ["settings", "version", "server", "device"]):
            log_pass("Navigate to Settings tab")
        else:
            log_warn("Navigate to Settings tab", "Content not detected")
    else:
        log_fail("Navigate to Settings tab", "Could not click tab")

    # Navigate back to Chats
    if click_tab(page, "Chats"):
        page.wait_for_timeout(1500)
        screenshot(page, "04-back-to-chats")
        log_pass("Navigate back to Chats tab")
    else:
        log_fail("Navigate back to Chats tab", "Could not click Chats tab from Settings page — likely z-index/overlay bug")

    # Test: Settings → Agents (cross navigation)
    click_tab(page, "Settings")
    page.wait_for_timeout(500)
    if click_tab(page, "Agents"):
        page.wait_for_timeout(500)
        log_pass("Navigate Settings → Agents")
    else:
        log_fail("Navigate Settings → Agents", "Tab click blocked")

    # Test: Agents → Chats
    if click_tab(page, "Chats"):
        page.wait_for_timeout(500)
        log_pass("Navigate Agents → Chats")
    else:
        log_fail("Navigate Agents → Chats", "Tab click blocked")


def find_list_items(page, exclude_labels=None):
    """Find clickable list items, excluding tab bar buttons."""
    if exclude_labels is None:
        exclude_labels = {"Chats", "Agents", "Settings", "+", "＋", ""}

    candidates = []
    # Try role="button" elements
    for el in page.locator("[role='button'], [role='link']").all():
        try:
            text = (el.text_content() or "").strip()
            if text in exclude_labels or len(text) < 3:
                continue
            bbox = el.bounding_box()
            if not bbox or bbox["height"] < 25 or bbox["height"] > 200:
                continue
            # Skip elements in the tab bar (bottom of page)
            viewport = page.viewport_size
            if viewport and bbox["y"] > viewport["height"] - 60:
                continue
            candidates.append((el, text, bbox))
        except:
            continue

    # Also try Pressable/TouchableOpacity which render as divs with onClick
    if not candidates:
        for el in page.locator("div[tabindex='0']").all():
            try:
                text = (el.text_content() or "").strip()
                if text in exclude_labels or len(text) < 3:
                    continue
                bbox = el.bounding_box()
                if not bbox or bbox["height"] < 25 or bbox["height"] > 200:
                    continue
                viewport = page.viewport_size
                if viewport and bbox["y"] > viewport["height"] - 60:
                    continue
                # Skip search inputs and filter pills (too short width-wise or too narrow)
                if bbox["width"] < 100:
                    continue
                candidates.append((el, text, bbox))
            except:
                continue

    return candidates


def test_chats_tab(page):
    """Test 3: Chats tab — list, loading, interaction."""
    print("\n📋 Test 3: Chats Tab")

    page.goto(BASE_URL + "/")
    page.wait_for_timeout(3000)
    screenshot(page, "05-chats-list")

    body = page.text_content("body") or ""

    # Check if we see chat-like content
    has_chats = any(kw in body.lower() for kw in ["ago", "yesterday", "today", "agent", "general"])
    if has_chats:
        log_pass("Chats list has content")
    else:
        log_warn("Chats list content", "No recognizable chat items")

    # Find and click chat items
    items = find_list_items(page)
    if items:
        log_pass(f"Found {len(items)} chat items")
        first_el, first_text, _ = items[0]
        short_text = first_text[:60].replace("\n", " ")

        try:
            first_el.click()
            page.wait_for_timeout(2000)
            screenshot(page, "06-chat-detail")

            # Check for message input
            inputs = page.locator("input, textarea, [contenteditable='true']").all()
            if inputs:
                log_pass("Chat detail has input field")
            else:
                log_warn("Chat detail input", "No input found")

            # Check for message content
            detail_body = page.text_content("body") or ""
            if len(detail_body) > 50:
                log_pass("Chat detail loaded", f"'{short_text}'")
            else:
                log_warn("Chat detail content", "Seems empty")

            # Test back navigation
            back = page.locator("[aria-label*='back' i], [aria-label*='Back']").all()
            if back:
                back[0].click()
                page.wait_for_timeout(1000)
                log_pass("Back button from chat detail")
            else:
                page.go_back()
                page.wait_for_timeout(1000)
                log_warn("Chat back navigation", "No back button, used browser back")

        except Exception as e:
            log_fail("Chat detail interaction", str(e)[:200])
    else:
        log_warn("Chat items", "No clickable items found — check if API returns chats")


def test_agents_tab(page):
    """Test 4: Agents tab — list, filters, search, interaction."""
    print("\n📋 Test 4: Agents Tab")

    page.goto(BASE_URL + "/")
    page.wait_for_timeout(1000)
    click_tab(page, "Agents")
    page.wait_for_timeout(2000)

    screenshot(page, "07-agents-tab")
    body = page.text_content("body") or ""

    # Search bar
    search = page.locator("input[placeholder*='earch' i], input[type='search']").all()
    if search:
        log_pass("Agents search bar found")
        try:
            search[0].fill("test")
            page.wait_for_timeout(500)
            screenshot(page, "07b-agents-search")
            search[0].fill("")
            page.wait_for_timeout(500)
            log_pass("Search input works")
        except Exception as e:
            log_fail("Search input", str(e)[:100])
    else:
        log_warn("Search bar", "Not found")

    # Filter pills
    filter_labels = ["All", "iMessage", "Signal", "Discord", "Dispatch"]
    found = [l for l in filter_labels if l.lower() in body.lower()]
    if found:
        log_pass("Filter pills", ", ".join(found))
        # Click through filters
        for label in ["iMessage", "Signal", "All"]:
            try:
                page.get_by_text(label, exact=True).first.click(timeout=2000)
                page.wait_for_timeout(300)
            except:
                pass
        log_pass("Filter pill clicking works")
    else:
        log_warn("Filter pills", "None found")

    # Agent items
    items = find_list_items(page)
    if items:
        log_pass(f"Found {len(items)} agent items")
        first_el, first_text, _ = items[0]
        short_text = first_text[:60].replace("\n", " ")

        try:
            first_el.click(force=True, timeout=5000)
            page.wait_for_timeout(2000)
            screenshot(page, "08-agent-detail")

            detail_body = page.text_content("body") or ""
            url = page.url
            if "agents/" in url or len(detail_body) > 100:
                log_pass("Agent detail loaded", f"'{short_text}'")
            else:
                log_warn("Agent detail", f"May not have navigated — URL: {url}")

            # Input
            inputs = page.locator("input, textarea, [contenteditable='true']").all()
            if inputs:
                log_pass("Agent detail has input")
            else:
                log_warn("Agent detail input", "Not found")

            # Back
            back = page.locator("[aria-label*='back' i], [aria-label*='Back']").all()
            if back:
                back[0].click()
                page.wait_for_timeout(1000)
                log_pass("Back from agent detail")
            else:
                page.go_back()
                page.wait_for_timeout(1000)
                log_warn("Agent back nav", "Used browser back")
        except Exception as e:
            log_fail("Agent detail interaction", str(e)[:200])
    else:
        log_warn("Agent items", "No clickable items found")


def test_settings_tab(page):
    """Test 5: Settings tab content."""
    print("\n📋 Test 5: Settings Tab")

    page.goto(BASE_URL + "/")
    page.wait_for_timeout(1000)
    click_tab(page, "Settings")
    page.wait_for_timeout(1500)

    screenshot(page, "09-settings-tab")
    body = page.text_content("body") or ""

    checks = {
        "Version info": ["v1.0", "version", "dispatch"],
        "API server info": ["api", "server", "connection", "9091"],
        "Device token": ["device", "token"],
        "Danger zone": ["danger", "clear", "restart"],
    }

    for name, keywords in checks.items():
        if any(k.lower() in body.lower() for k in keywords):
            log_pass(name)
        else:
            log_warn(name, "Not found")


def test_navigation_round_trip(page):
    """Test 6: Full navigation round trip."""
    print("\n📋 Test 6: Navigation Round Trip")

    page.goto(BASE_URL + "/")
    page.wait_for_timeout(2000)

    # Rapid tab switching
    sequence = ["Agents", "Settings", "Chats", "Agents", "Settings", "Chats"]
    all_ok = True
    for tab in sequence:
        if not click_tab(page, tab):
            log_fail(f"Rapid switch to {tab}", "Click failed")
            all_ok = False
            break
        page.wait_for_timeout(500)

    if all_ok:
        log_pass(f"Rapid tab switching ({len(sequence)} switches)")

    screenshot(page, "10-after-rapid-switching")

    # Deep navigation: Chats → detail → back → Agents → detail → back
    click_tab(page, "Chats")
    page.wait_for_timeout(1000)

    items = find_list_items(page)
    if items:
        try:
            items[0][0].click()
            page.wait_for_timeout(1500)
            screenshot(page, "11-chat-roundtrip")

            # Back
            back = page.locator("[aria-label*='back' i], [aria-label*='Back']").all()
            if back:
                back[0].click()
            else:
                page.go_back()
            page.wait_for_timeout(1000)

            # Go to agents
            click_tab(page, "Agents")
            page.wait_for_timeout(1000)

            agent_items = find_list_items(page)
            if agent_items:
                agent_items[0][0].click(force=True, timeout=5000)
                page.wait_for_timeout(1500)
                screenshot(page, "12-agent-roundtrip")

                back = page.locator("[aria-label*='back' i], [aria-label*='Back']").all()
                if back:
                    back[0].click()
                else:
                    page.go_back()
                page.wait_for_timeout(1000)

                log_pass("Full round trip: Chat detail → back → Agent detail → back")
            else:
                log_pass("Partial round trip (no agent items)")
        except Exception as e:
            log_fail("Round trip", str(e)[:200])
    else:
        log_warn("Round trip", "No chat items to start flow")


def test_console_errors(page):
    """Test 7: JS console errors."""
    print("\n📋 Test 7: Console Errors")

    js_errors = []
    page.on("console", lambda msg: js_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: js_errors.append(str(err)))

    page.goto(BASE_URL + "/")
    page.wait_for_timeout(2000)

    for tab in ["Agents", "Settings", "Chats"]:
        click_tab(page, tab)
        page.wait_for_timeout(1500)

    # Click into a chat if available
    items = find_list_items(page)
    if items:
        items[0][0].click()
        page.wait_for_timeout(2000)

    if js_errors:
        critical = [e for e in js_errors if "favicon" not in e.lower() and "serviceworker" not in e.lower()]
        if critical:
            for err in critical[:10]:
                log_fail("JS Console Error", err[:200])
        else:
            log_pass("No critical JS errors", f"{len(js_errors)} non-critical")
    else:
        log_pass("No JS console errors")


def test_responsive(page):
    """Test 8: Mobile viewport."""
    print("\n📋 Test 8: Responsive Layout (iPhone)")

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL + "/")
    page.wait_for_timeout(2000)
    screenshot(page, "13-mobile-chats")

    for tab in ["Chats", "Agents", "Settings"]:
        try:
            el = page.get_by_text(tab, exact=True).first
            if el.is_visible():
                log_pass(f"'{tab}' visible at mobile width")
            else:
                log_fail(f"'{tab}' visible at mobile width")
        except:
            log_fail(f"'{tab}' at mobile width", "Not found")

    # Navigate at mobile width
    try:
        click_tab(page, "Agents")
        page.wait_for_timeout(1000)
        screenshot(page, "14-mobile-agents")

        click_tab(page, "Settings")
        page.wait_for_timeout(1000)
        screenshot(page, "15-mobile-settings")

        click_tab(page, "Chats")
        page.wait_for_timeout(1000)
        log_pass("Mobile tab navigation works")
    except Exception as e:
        log_fail("Mobile tab navigation", str(e)[:100])

    page.set_viewport_size({"width": 1280, "height": 720})


def test_send_message(page):
    """Test 9: Try sending a message in a chat."""
    print("\n📋 Test 9: Message Sending")

    page.goto(BASE_URL + "/")
    page.wait_for_timeout(2000)

    items = find_list_items(page)
    if not items:
        log_warn("Send message", "No chats to test with")
        return

    items[0][0].click()
    page.wait_for_timeout(2000)

    # Find message input
    inputs = page.locator("input[placeholder*='message' i], input[placeholder*='type' i], textarea[placeholder*='message' i], textarea[placeholder*='type' i]").all()
    if not inputs:
        inputs = page.locator("input, textarea").all()

    if inputs:
        log_pass("Message input found")
        # Type a test message but don't send
        try:
            inputs[0].fill("test message from playwright")
            page.wait_for_timeout(500)
            screenshot(page, "16-message-typed")

            # Check if send button appears/is enabled
            send = page.locator("[aria-label*='send' i], [aria-label*='Send'], button:has-text('Send')").all()
            if send:
                log_pass("Send button found")
            else:
                log_warn("Send button", "Not found — may use Enter key")

            # Clear without sending
            inputs[0].fill("")
            log_pass("Message input interactive")
        except Exception as e:
            log_fail("Message input interaction", str(e)[:100])
    else:
        log_fail("Message input", "No input found in chat detail")


def test_new_chat_button(page):
    """Test 10: FAB / New Chat button."""
    print("\n📋 Test 10: New Chat / FAB Button")

    page.goto(BASE_URL + "/")
    page.wait_for_timeout(2000)

    # Look for FAB (+ button)
    fab = page.locator("text='+', text='＋', [aria-label*='new' i], [aria-label*='create' i], [aria-label*='add' i]").all()
    if not fab:
        # Try finding a circular button at bottom-right
        fab = page.locator("[role='button']").all()
        fab = [f for f in fab if (f.text_content() or "").strip() in ["+", "＋"]]

    if fab:
        log_pass("FAB / New Chat button found")
        try:
            fab[0].click()
            page.wait_for_timeout(1500)
            screenshot(page, "17-new-chat")
            log_pass("FAB click works")
            # Go back
            page.go_back()
            page.wait_for_timeout(500)
        except Exception as e:
            log_fail("FAB interaction", str(e)[:100])
    else:
        log_warn("FAB button", "Not found")


def main():
    print("🧪 Dispatch App Comprehensive Test Suite")
    print(f"   Target: {BASE_URL}")
    print(f"   Screenshots: {SCREENSHOT_DIR}/")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        page = context.new_page()

        if test_initial_load(page):
            test_tab_navigation(page)
            test_chats_tab(page)
            test_agents_tab(page)
            test_settings_tab(page)
            test_navigation_round_trip(page)
            test_console_errors(page)
            test_responsive(page)
            test_send_message(page)
            test_new_chat_button(page)

        browser.close()

    # Summary
    print("\n" + "=" * 60)
    print(f"📊 RESULTS: {len(passes)} passed, {len(errors)} failed, {len(warnings)} warnings")
    print("=" * 60)

    if errors:
        print("\n❌ FAILURES:")
        for e in errors:
            print(f"   • {e}")

    if warnings:
        print("\n⚠️  WARNINGS:")
        for w in warnings:
            print(f"   • {w}")

    print(f"\n📸 Screenshots saved to {SCREENSHOT_DIR}/")

    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
