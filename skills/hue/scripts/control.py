#!/usr/bin/env -S uv run --script
"""
Philips Hue control — multi-bridge, auto-discovery, full API.

LIGHTS:
    list [bridge]                   List all lights (alias: ls)
    on <light>                      Turn on a light
    off <light>                     Turn off a light
    toggle <light>                  Toggle on/off
    brightness <light> <0-254>      Set brightness (alias: bri)
    color <light> <hue> <sat>       Set color (hue 0-65535, sat 0-254)
    temp <light> <153-500>          Color temp in mireds (alias: ct)
    alert <light> [long]            Flash once, or 15s with 'long'

ROOMS:
    room list                       List all rooms/groups
    room on <room>                  Turn on all lights in room
    room off <room>                 Turn off all lights in room
    room blink <room> [seconds]     Blink room (off, wait, on)

SCENES:
    scenes [bridge]                 List all scenes
    scene <name>                    Activate a scene by name

BRIDGES:
    bridges                         Show configured bridges + connectivity
    discover                        Find bridges on network (N-UPnP)
    pair <ip>                       Pair with a bridge (press button first!)
    status                          Full health check

OPTIONS (work anywhere in command):
    --transition <seconds>          Transition time (default: instant)
    --bridge <name>                 Target a specific bridge
    --json                          JSON output (works with list, room list,
                                    scenes, bridges)
    --quiet                         Suppress OK messages (for scripting)

Partial name matching: 'Kitchen' matches 'Kitchen Ceiling 1'.
Errors go to stderr, data to stdout — safe for piping.
"""

import sys
import os

# Add scripts dir to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hue_lib.config import load_bridges
from hue_lib.api import HueAPI
from hue_lib.commands import COMMANDS


def pop_flag(args, flag, has_value=True):
    """Remove a flag from args list and return its value. Position-independent."""
    for i, arg in enumerate(args):
        if arg == flag:
            if has_value and i + 1 < len(args):
                val = args[i + 1]
                del args[i:i + 2]
                return val
            elif not has_value:
                del args[i]
                return True
    return None


def main():
    args = list(sys.argv[1:])

    if not args or args[0] in ("--help", "-h"):
        print(__doc__)
        sys.exit(0)

    # Extract global flags (position-independent)
    transition = pop_flag(args, "--transition")
    bridge_filter = pop_flag(args, "--bridge")
    as_json = pop_flag(args, "--json", has_value=False)
    quiet = pop_flag(args, "--quiet", has_value=False)

    if not args:
        print(__doc__)
        sys.exit(1)

    command = args[0].lower()

    if command not in COMMANDS:
        # Suggest close matches: prefix OR substring
        close = set()
        if len(command) >= 2:
            for c in COMMANDS:
                if c.startswith(command[:2]) or command in c or c in command:
                    close.add(c)
        print(f"Unknown command: {command}", file=sys.stderr)
        if close:
            print(f"Did you mean: {', '.join(sorted(close))}?", file=sys.stderr)
        print("Run 'control.py --help' for usage.", file=sys.stderr)
        sys.exit(1)

    # Build context
    bridges = load_bridges()
    apis = {key: HueAPI(key, config) for key, config in bridges.items()}

    ctx = {
        "apis": apis,
        "bridges": bridges,
        "bridge_filter": bridge_filter,
        "transition": transition,
        "as_json": as_json,
        "quiet": quiet,
    }

    # Dispatch
    COMMANDS[command](ctx, args[1:])


if __name__ == "__main__":
    main()
