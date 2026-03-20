#!/usr/bin/env -S uv run --script
"""
System info dashboard showing CPU, memory, and process breakdown.

Usage:
    sysinfo.py          # Full dashboard
    sysinfo.py --json   # JSON output for programmatic use
"""

import subprocess
import json
import argparse
import re
from pathlib import Path


def get_system_specs():
    """Get total RAM and CPU cores."""
    ram_bytes = int(subprocess.run(
        ["sysctl", "-n", "hw.memsize"],
        capture_output=True, text=True
    ).stdout.strip())

    cpu_cores = int(subprocess.run(
        ["sysctl", "-n", "hw.ncpu"],
        capture_output=True, text=True
    ).stdout.strip())

    return {
        "ram_gb": ram_bytes / (1024**3),
        "cpu_cores": cpu_cores
    }


def get_top_stats():
    """Parse top output for current usage."""
    result = subprocess.run(
        ["top", "-l", "1", "-n", "0"],
        capture_output=True, text=True
    )

    stats = {}
    for line in result.stdout.split("\n"):
        if line.startswith("Load Avg:"):
            # Load Avg: 4.07, 4.81, 6.84
            match = re.search(r"Load Avg: ([\d.]+)", line)
            if match:
                stats["load_avg"] = float(match.group(1))
        elif line.startswith("CPU usage:"):
            # CPU usage: 22.8% user, 22.8% sys, 55.82% idle
            match = re.search(r"([\d.]+)% idle", line)
            if match:
                stats["cpu_idle_pct"] = float(match.group(1))
                stats["cpu_used_pct"] = 100 - stats["cpu_idle_pct"]
        elif line.startswith("PhysMem:"):
            # PhysMem: 7362M used (1861M wired, 2620M compressor), 148M unused.
            used_match = re.search(r"([\d.]+)([MG]) used", line)
            unused_match = re.search(r"([\d.]+)([MG]) unused", line)
            compressor_match = re.search(r"([\d.]+)([MG]) compressor", line)

            if used_match:
                val = float(used_match.group(1))
                unit = used_match.group(2)
                stats["mem_used_mb"] = val * 1024 if unit == "G" else val

            if unused_match:
                val = float(unused_match.group(1))
                unit = unused_match.group(2)
                stats["mem_free_mb"] = val * 1024 if unit == "G" else val

            if compressor_match:
                val = float(compressor_match.group(1))
                unit = compressor_match.group(2)
                stats["mem_compressed_mb"] = val * 1024 if unit == "G" else val

    return stats


def get_claude_processes():
    """Get all Claude processes with memory usage."""
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True, text=True
    )

    processes = []
    for line in result.stdout.split("\n"):
        if "2.1." in line or "claude" in line.lower():
            if "grep" in line:
                continue
            parts = line.split()
            if len(parts) >= 11:
                pid = parts[1]
                cpu = float(parts[2])
                mem_pct = float(parts[3])

                # Get memory in MB from RSS (column 6, in KB on macOS)
                try:
                    rss_kb = int(parts[5])
                    mem_mb = rss_kb / 1024
                except:
                    mem_mb = 0

                # Extract command info
                cmd = " ".join(parts[10:])

                # Categorize
                if "--chrome-native-host" in cmd:
                    category = "chrome-host"
                elif "--claude-in-chrome-mcp" in cmd:
                    category = "chrome-mcp"
                elif "transcripts/" in cmd:
                    # Extract session name from path
                    match = re.search(r"transcripts/([^/\s]+)", cmd)
                    category = f"session:{match.group(1)}" if match else "session"
                elif "-r" in cmd or "--dangerously-skip-permissions" in cmd:
                    category = "interactive"
                else:
                    category = "other"

                processes.append({
                    "pid": pid,
                    "cpu_pct": cpu,
                    "mem_pct": mem_pct,
                    "mem_mb": round(mem_mb, 1),
                    "category": category,
                    "cmd_short": cmd[:60]
                })

    return processes


def get_sdk_sessions():
    """Get active SDK sessions from the registry."""
    registry_path = Path.home() / "dispatch/state/sessions.json"
    if not registry_path.exists():
        return []

    try:
        with open(registry_path) as f:
            registry = json.load(f)

        sessions = []
        for chat_id, info in registry.get("sessions", {}).items():
            sessions.append({
                "name": info.get("session_name", chat_id),
                "tier": info.get("tier", "unknown"),
                "status": info.get("status", "unknown")
            })
        return sessions
    except (json.JSONDecodeError, KeyError):
        return []


def get_chrome_tabs():
    """Get Chrome tab counts per profile."""
    chrome_cli = Path.home() / "code/chrome-control/chrome"
    if not chrome_cli.exists():
        return []

    profiles = []

    # Try each profile
    for profile_idx in range(2):
        try:
            result = subprocess.run(
                [str(chrome_cli), "-p", str(profile_idx), "tabs"],
                capture_output=True, text=True,
                timeout=3
            )

            if result.returncode == 0:
                tabs = [l for l in result.stdout.strip().split("\n") if l and not l.startswith(" ")]
                profiles.append({
                    "profile": profile_idx,
                    "tab_count": len(tabs)
                })
        except subprocess.TimeoutExpired:
            profiles.append({
                "profile": profile_idx,
                "tab_count": -1,
                "error": "timeout"
            })
        except Exception as e:
            profiles.append({
                "profile": profile_idx,
                "tab_count": -1,
                "error": str(e)
            })

    return profiles


def get_chrome_processes():
    """Get Chrome process memory usage."""
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True, text=True
    )

    total_mem_mb = 0
    total_cpu = 0
    process_count = 0

    for line in result.stdout.split("\n"):
        if "Google Chrome" in line and "grep" not in line:
            parts = line.split()
            if len(parts) >= 6:
                try:
                    cpu = float(parts[2])
                    rss_kb = int(parts[5])
                    total_mem_mb += rss_kb / 1024
                    total_cpu += cpu
                    process_count += 1
                except:
                    pass

    return {
        "process_count": process_count,
        "total_mem_mb": round(total_mem_mb, 1),
        "total_cpu_pct": round(total_cpu, 1)
    }


def format_mb(mb):
    """Format MB nicely."""
    if mb >= 1024:
        return f"{mb/1024:.1f}GB"
    return f"{mb:.0f}MB"


def print_dashboard(data):
    """Print a nice dashboard."""
    specs = data["specs"]
    stats = data["stats"]
    claude = data["claude_processes"]
    sdk = data["sdk_sessions"]
    chrome_tabs = data["chrome_tabs"]
    chrome_procs = data["chrome_processes"]

    print("=" * 50)
    print("  SYSTEM DASHBOARD")
    print("=" * 50)
    print()

    # System specs
    print(f"System: {specs['ram_gb']:.0f}GB RAM, {specs['cpu_cores']} cores")
    print()

    # Memory
    mem_total = stats.get("mem_used_mb", 0) + stats.get("mem_free_mb", 0)
    mem_used_pct = (stats.get("mem_used_mb", 0) / mem_total * 100) if mem_total else 0
    print("MEMORY")
    print(f"  Used:       {format_mb(stats.get('mem_used_mb', 0)):>8} ({mem_used_pct:.0f}%)")
    print(f"  Free:       {format_mb(stats.get('mem_free_mb', 0)):>8}")
    print(f"  Compressed: {format_mb(stats.get('mem_compressed_mb', 0)):>8}")

    # Memory pressure indicator
    if stats.get("mem_free_mb", 0) < 200:
        print(f"  Status:     {'CRITICAL':>8} (< 200MB free)")
    elif stats.get("mem_free_mb", 0) < 500:
        print(f"  Status:     {'WARNING':>8} (< 500MB free)")
    else:
        print(f"  Status:     {'OK':>8}")
    print()

    # CPU
    print("CPU")
    print(f"  Used:       {stats.get('cpu_used_pct', 0):>7.1f}%")
    print(f"  Load Avg:   {stats.get('load_avg', 0):>7.2f}")
    print()

    # Claude processes
    print("CLAUDE PROCESSES")
    claude_total_mem = sum(p["mem_mb"] for p in claude)
    claude_total_cpu = sum(p["cpu_pct"] for p in claude)
    print(f"  Count:      {len(claude):>8}")
    print(f"  Memory:     {format_mb(claude_total_mem):>8}")
    print(f"  CPU:        {claude_total_cpu:>7.1f}%")

    # Breakdown by category
    categories = {}
    for p in claude:
        cat = p["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "mem_mb": 0}
        categories[cat]["count"] += 1
        categories[cat]["mem_mb"] += p["mem_mb"]

    if categories:
        print("  Breakdown:")
        for cat, info in sorted(categories.items(), key=lambda x: -x[1]["mem_mb"]):
            print(f"    {cat}: {info['count']} ({format_mb(info['mem_mb'])})")
    print()

    # SDK sessions
    print("SDK SESSIONS")
    print(f"  Active:     {len(sdk):>8}")
    if sdk:
        print(f"  Sessions:   {', '.join(s['name'] for s in sdk[:5])}")
    print()

    # Chrome
    print("CHROME")
    print(f"  Processes:  {chrome_procs['process_count']:>8}")
    print(f"  Memory:     {format_mb(chrome_procs['total_mem_mb']):>8}")
    print(f"  CPU:        {chrome_procs['total_cpu_pct']:>7.1f}%")
    for profile in chrome_tabs:
        if profile.get("error"):
            print(f"  Profile {profile['profile']}:  {'N/A':>8} ({profile['error']})")
        else:
            print(f"  Profile {profile['profile']}:  {profile['tab_count']:>8} tabs")
    print()

    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="System info dashboard")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    data = {
        "specs": get_system_specs(),
        "stats": get_top_stats(),
        "claude_processes": get_claude_processes(),
        "sdk_sessions": get_sdk_sessions(),
        "chrome_tabs": get_chrome_tabs(),
        "chrome_processes": get_chrome_processes()
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_dashboard(data)


if __name__ == "__main__":
    main()
