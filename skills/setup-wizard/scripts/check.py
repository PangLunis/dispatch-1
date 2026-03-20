#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
Dispatch System Setup Wizard
Checks ALL requirements for the personal assistant system on macOS.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"
WARN = f"{YELLOW}⚠{RESET}"
INFO = f"{BLUE}ℹ{RESET}"

results = {"pass": 0, "fail": 0, "warn": 0}


def check(name, passed, fix_hint=None, required=True, fix_cmd=None):
    if passed:
        results["pass"] += 1
        if not QUIET:
            print(f"  {PASS} {name}")
    elif required:
        results["fail"] += 1
        print(f"  {FAIL} {name}")
        if fix_hint:
            print(f"     {fix_hint}")
        if fix_cmd and AUTO_FIX:
            print(f"     → Auto-fixing: {fix_cmd}")
            os.system(fix_cmd)
    else:
        results["warn"] += 1
        print(f"  {WARN} {name} (optional)")
        if fix_hint:
            print(f"     {fix_hint}")


def cmd_exists(name):
    return shutil.which(name) is not None


def file_exists(path):
    return Path(path).expanduser().exists()


def dir_exists(path):
    return Path(path).expanduser().is_dir()


def can_read_file(path):
    p = Path(path).expanduser()
    return p.exists() and os.access(p, os.R_OK)


def can_write_dir(path):
    p = Path(path).expanduser()
    return p.exists() and os.access(p, os.W_OK)


def run_silent(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def check_tcc_permission(service_name, test_fn):
    """Check TCC permission by attempting the operation."""
    try:
        return test_fn()
    except Exception:
        return False


# ─── PHASE 1: System Tools ───────────────────────────────────────────────

def phase1_system_tools():
    print(f"\n{BOLD}Phase 1: System Tools{RESET}")

    # Xcode Command Line Tools
    xcode_ok = run_silent("xcode-select -p")
    check("Xcode Command Line Tools", xcode_ok,
          fix_hint="Run: xcode-select --install",
          fix_cmd="xcode-select --install" if AUTO_FIX else None)

    # Homebrew
    check("Homebrew", cmd_exists("brew"),
          fix_hint='Run: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')

    # tmux
    check("tmux", cmd_exists("tmux"),
          fix_hint="Run: brew install tmux",
          fix_cmd="brew install tmux" if AUTO_FIX else None)

    # cliclick
    check("cliclick", cmd_exists("cliclick"),
          fix_hint="Run: brew install cliclick",
          fix_cmd="brew install cliclick" if AUTO_FIX else None)

    # uv
    check("uv (Python package manager)", cmd_exists("uv"),
          fix_hint="Run: curl -LsSf https://astral.sh/uv/install.sh | sh")

    # Claude CLI
    check("Claude CLI", cmd_exists("claude"),
          fix_hint="Run: curl -fsSL https://code.claude.com/cli/install | bash")

    # signal-cli (optional)
    check("signal-cli", cmd_exists("signal-cli"),
          fix_hint="Run: brew install signal-cli",
          required=False)


# ─── PHASE 2: TCC Permissions ────────────────────────────────────────────

def phase2_tcc_permissions():
    print(f"\n{BOLD}Phase 2: macOS Permissions (TCC){RESET}")
    print(f"  {INFO} These require manual grant in System Settings > Privacy & Security")

    # Messages database access (Full Disk Access test)
    messages_db = Path.home() / "Library" / "Messages" / "chat.db"
    messages_ok = False
    if messages_db.exists():
        try:
            conn = sqlite3.connect(str(messages_db))
            conn.execute("SELECT COUNT(*) FROM message LIMIT 1")
            conn.close()
            messages_ok = True
        except Exception:
            pass
    check("Messages.app database access (Full Disk Access)",
          messages_ok,
          fix_hint="System Settings > Privacy & Security > Full Disk Access > Add Terminal/iTerm2")

    # Contacts access (test via AppleScript)
    contacts_ok = run_silent(
        'osascript -e \'tell application "Contacts" to count of people\' 2>/dev/null')
    check("Contacts.app access",
          contacts_ok,
          fix_hint="System Settings > Privacy & Security > Contacts > Allow Terminal")

    # Reminders access
    reminders_ok = run_silent(
        'osascript -e \'tell application "Reminders" to count of lists\' 2>/dev/null')
    check("Reminders.app access",
          reminders_ok,
          fix_hint="System Settings > Privacy & Security > Reminders > Allow Terminal",
          required=False)

    # Accessibility (cliclick test)
    accessibility_ok = run_silent("cliclick p:. 2>/dev/null")
    check("Accessibility access (cliclick)",
          accessibility_ok,
          fix_hint="System Settings > Privacy & Security > Accessibility > Add Terminal",
          required=False)

    # Automation (AppleScript to Messages)
    automation_ok = run_silent(
        'osascript -e \'tell application "Messages" to count of chats\' 2>/dev/null')
    check("Automation: Messages.app (for sending iMessages)",
          automation_ok,
          fix_hint="System Settings > Privacy & Security > Automation > Terminal > Messages.app")


# ─── PHASE 3: API Keys & Secrets ─────────────────────────────────────────

def phase3_api_keys():
    print(f"\n{BOLD}Phase 3: API Keys & Secrets{RESET}")

    check("~/.claude/secrets.env",
          file_exists("~/.claude/secrets.env"),
          fix_hint="Create ~/.claude/secrets.env with required API keys")

    check("TTS API key (~/.claude/skills/tts/.env)",
          file_exists("~/.claude/skills/tts/.env"),
          fix_hint="Create with GOOGLE_TTS_API_KEY=...",
          required=False)

    check("Gemini API key (~/.claude/secrets.env)",
          file_exists("~/.claude/secrets.env"),
          fix_hint="Add GEMINI_API_KEY to ~/.claude/secrets.env",
          required=False)

    # Check if Anthropic API key is accessible
    anthropic_ok = os.environ.get("ANTHROPIC_API_KEY") is not None
    if not anthropic_ok:
        # Check if it's in secrets.env
        secrets_path = Path.home() / ".claude" / "secrets.env"
        if secrets_path.exists():
            content = secrets_path.read_text()
            anthropic_ok = "ANTHROPIC_API_KEY" in content
    check("Anthropic API key",
          anthropic_ok,
          fix_hint="Set ANTHROPIC_API_KEY in environment or ~/.claude/secrets.env")


# ─── PHASE 4: Chrome Extension ───────────────────────────────────────────

def phase4_chrome():
    print(f"\n{BOLD}Phase 4: Chrome Extension{RESET}")

    chrome_dir = Path.home() / ".claude" / "skills" / "chrome-control" / "scripts"
    check("Chrome control directory exists",
          chrome_dir.is_dir(),
          fix_hint="Ensure ~/.claude/skills symlink points to skills directory")

    native_host_manifest = (Path.home() / "Library" / "Application Support" /
                            "Google" / "Chrome" / "NativeMessagingHosts" /
                            "com.dispatch.chrome_control.json")
    check("Native messaging host manifest",
          native_host_manifest.exists(),
          fix_hint="Run: ~/.claude/skills/chrome-control/scripts/install_native_host.sh")

    chrome_cli = chrome_dir / "chrome"
    check("Chrome CLI executable",
          chrome_cli.exists() and os.access(chrome_cli, os.X_OK),
          fix_hint="Check ~/.claude/skills/chrome-control/scripts/chrome exists and is executable")

    # Test connection
    chrome_ping = run_silent(f"{chrome_cli} ping 2>/dev/null") if chrome_cli.exists() else False
    check("Chrome extension responding",
          chrome_ping,
          fix_hint="Open Chrome, go to chrome://extensions/, ensure extension is loaded and enabled",
          required=False)


# ─── PHASE 5: Smart Home ─────────────────────────────────────────────────

def phase5_smart_home():
    print(f"\n{BOLD}Phase 5: Smart Home (Optional){RESET}")

    # Hue
    hue_dir = Path.home() / ".hue"
    check("Hue config directory (~/.hue/)",
          hue_dir.is_dir(),
          fix_hint="Create ~/.hue/ and add bridge configs (home.json, office.json)",
          required=False)

    if hue_dir.is_dir():
        for name in ["home.json", "office.json"]:
            path = hue_dir / name
            check(f"  Hue bridge config: {name}",
                  path.exists(),
                  fix_hint=f"Create {path} with bridge_ip, username, bridge_name",
                  required=False)

    # Lutron
    lutron_dir = Path.home() / ".config" / "pylutron_caseta"
    check("Lutron Caseta certificates",
          lutron_dir.is_dir(),
          fix_hint="Run Lutron pairing script to generate certificates in ~/.config/pylutron_caseta/",
          required=False)

    if lutron_dir.is_dir():
        certs = list(lutron_dir.glob("*.crt")) + list(lutron_dir.glob("*.key"))
        check(f"  Lutron cert files ({len(certs)} found)",
              len(certs) >= 3,
              fix_hint="Need: {bridge_ip}.crt, {bridge_ip}.key, {bridge_ip}-bridge.crt",
              required=False)

    # Sonos (just check if soco is importable)
    sonos_ok = run_silent("uv run python -c 'import soco' 2>/dev/null")
    check("Sonos library (soco)",
          sonos_ok,
          fix_hint="Run: uv pip install soco",
          required=False)


# ─── PHASE 6: Daemon & LaunchAgents ──────────────────────────────────────

def phase6_daemon():
    print(f"\n{BOLD}Phase 6: Daemon & LaunchAgents{RESET}")

    # LaunchAgent plists
    la_dir = Path.home() / "Library" / "LaunchAgents"
    daemon_plist = la_dir / "com.dispatch.claude-assistant.plist"
    check("Daemon LaunchAgent plist",
          daemon_plist.exists(),
          fix_hint="Run: claude-assistant install")

    menubar_plist = la_dir / "com.dispatch.claude-menubar.plist"
    check("Menubar LaunchAgent plist",
          menubar_plist.exists(),
          fix_hint="Run: claude-assistant menubar-install",
          required=False)

    chat_viewer_plist = la_dir / "com.dispatch.chat-viewer.plist"
    check("Chat viewer LaunchAgent plist",
          chat_viewer_plist.exists(),
          required=False)

    # State directory
    state_dir = Path.home() / "dispatch" / "state"
    check("Daemon state directory",
          state_dir.is_dir(),
          fix_hint="Run: mkdir -p ~/dispatch/state")

    check("Session registry (sessions.json)",
          (state_dir / "sessions.json").exists() if state_dir.is_dir() else False,
          fix_hint="Created automatically on first daemon run",
          required=False)

    # Logs directory
    logs_dir = Path.home() / "dispatch" / "logs"
    check("Daemon logs directory",
          logs_dir.is_dir() and can_write_dir(logs_dir),
          fix_hint="Run: mkdir -p ~/dispatch/logs")

    # Daemon running check
    daemon_running = run_silent("claude-assistant status 2>/dev/null | grep -q 'running'")
    check("Daemon currently running",
          daemon_running,
          fix_hint="Run: claude-assistant start",
          required=False)

    # tmux sessions
    tmux_running = run_silent("tmux ls 2>/dev/null")
    check("tmux server running",
          tmux_running,
          required=False)


# ─── PHASE 7: Databases & Storage ────────────────────────────────────────

def phase7_databases():
    print(f"\n{BOLD}Phase 7: Databases & Storage{RESET}")

    # Messages DB
    messages_db = Path.home() / "Library" / "Messages" / "chat.db"
    check("Messages.app database exists",
          messages_db.exists(),
          fix_hint="Messages.app must be set up with an iCloud/Apple ID account")

    # Memory DuckDB
    memory_db = Path.home() / ".claude" / "memory.duckdb"
    check("Memory database (~/.claude/memory.duckdb)",
          memory_db.exists(),
          fix_hint="Run: uv run ~/.claude/skills/memory/scripts/memory.py init",
          required=False)

    # Transcripts directory
    transcripts = Path.home() / "transcripts"
    check("Transcripts directory (~/transcripts/)",
          transcripts.is_dir(),
          fix_hint="Run: mkdir -p ~/transcripts")

    # .claude symlink check
    claude_dir = Path.home() / ".claude"
    check("~/.claude/ directory exists",
          claude_dir.is_dir())

    check("~/.claude/skills/ directory exists",
          (claude_dir / "skills").is_dir())

    check("~/.claude/SOUL.md exists",
          (claude_dir / "SOUL.md").exists(),
          fix_hint="Create ~/.claude/SOUL.md with personality definition",
          required=False)



# ─── PHASE 8: Code Repositories ──────────────────────────────────────────

def phase8_repos():
    print(f"\n{BOLD}Phase 8: Code Repositories{RESET}")

    repos = {
        "claude-assistant": "Main daemon",
        "sms-cli": "SMS send/read CLI",
        "contacts-cli": "Contact lookup + tier management",
        "chrome-control": "Chrome browser automation",
        "nano-banana": "Image generation (Gemini)",
        "chat-viewer": "Web UI for transcripts",
    }

    for repo, desc in repos.items():
        path = Path.home() / "code" / repo
        check(f"~/code/{repo}/ ({desc})",
              path.is_dir(),
              fix_hint=f"Clone {repo} to ~/code/{repo}/",
              required=(repo in ["claude-assistant", "sms-cli", "contacts-cli"]))


# ─── PHASE 9: Xcode (for iOS development) ────────────────────────────────

def phase9_xcode():
    print(f"\n{BOLD}Phase 9: Xcode & iOS Development (Optional){RESET}")

    xcode_app = Path("/Applications/Xcode.app")
    check("Xcode.app installed",
          xcode_app.exists(),
          fix_hint="Install from Mac App Store",
          required=False)

    if xcode_app.exists():
        # Check license accepted
        license_ok = run_silent("sudo xcodebuild -checkFirstLaunchStatus 2>/dev/null")
        check("Xcode license accepted",
              license_ok,
              fix_hint="Run: sudo xcodebuild -license accept (requires admin password)",
              required=False)

        # Check iOS simulators
        simulators_ok = run_silent("xcrun simctl list devices 2>/dev/null | grep -q 'iPhone'")
        check("iOS simulators available",
              simulators_ok,
              fix_hint="Open Xcode > Settings > Platforms > Download iOS simulator",
              required=False)

    # Apple Developer account (can't check programmatically)
    check("Apple Developer Program ($99/yr)",
          False,  # Can't verify
          fix_hint="Enroll at https://developer.apple.com/programs/enroll/ (needed for TestFlight)",
          required=False)


# ─── MAIN ────────────────────────────────────────────────────────────────

def main():
    global AUTO_FIX, QUIET

    AUTO_FIX = "--fix" in sys.argv
    QUIET = "--quiet" in sys.argv

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Dispatch System Setup Wizard{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    if AUTO_FIX:
        print(f"  {INFO} Auto-fix mode enabled (will attempt to install missing tools)")

    phase1_system_tools()
    phase2_tcc_permissions()
    phase3_api_keys()
    phase4_chrome()
    phase5_smart_home()
    phase6_daemon()
    phase7_databases()
    phase8_repos()
    phase9_xcode()

    # Summary
    total = results["pass"] + results["fail"] + results["warn"]
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"  {PASS} {results['pass']} passed  {FAIL} {results['fail']} failed  {WARN} {results['warn']} warnings  ({total} total)")

    if results["fail"] == 0:
        print(f"\n  {GREEN}{BOLD}System is fully configured!{RESET}")
    else:
        print(f"\n  {RED}{BOLD}{results['fail']} critical items need attention.{RESET}")
        print(f"  Run with --fix to auto-install missing tools.")
        print(f"  TCC permissions must be granted manually in System Settings.")

    print()
    return 1 if results["fail"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
