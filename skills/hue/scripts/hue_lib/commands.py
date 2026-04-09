"""Command handlers for Hue CLI.

Each function receives a context dict with:
    apis:           {key: HueAPI} — bridge API clients
    bridges:        {key: config} — bridge configuration
    bridge_filter:  Optional bridge name filter
    transition:     Optional transition time in seconds (str)
    as_json:        Whether to output JSON
    quiet:          Suppress OK messages (for scripting)
"""

import json
import sys
import time

from .api import HueAPI
from .discovery import discover_bridges, get_bridge_config, pair_bridge
from .resolve import find_entity
from .display import (
    format_light_list, format_room_list, format_scene_list,
    format_bridge_status, format_discovery, format_status_discovery,
    format_match_list
)


# --- Helpers ---

def err(msg):
    """Print error message to stderr."""
    print(f"ERROR: {msg}", file=sys.stderr)


def get_all(ctx, entity_getter):
    """Get all entities from all (or filtered) bridges."""
    all_items = {}
    for key, api in ctx["apis"].items():
        bf = ctx.get("bridge_filter")
        if bf and bf.lower() != key.lower():
            continue
        all_items.update(getattr(api, entity_getter)())
    return all_items


def resolve(name, entities, entity_type):
    """Find entity by name, print match/not-found message if needed."""
    entity, matches = find_entity(name, entities, entity_type)
    if entity:
        return entity
    if matches:
        print(format_match_list(entity_type, name, matches), file=sys.stderr)
    else:
        err(f"{entity_type.title()} '{name}' not found")
    return None


def set_light(ctx, light, state):
    """Set light state via the correct bridge API."""
    api = ctx["apis"].get(light["bridge"])
    if not api:
        err(f"Bridge '{light['bridge']}' not found")
        return False
    return api.set_light_state(light["id"], state)


def set_group(ctx, group, state):
    """Set group state via the correct bridge API."""
    api = ctx["apis"].get(group["bridge"])
    if not api:
        err(f"Bridge '{group['bridge']}' not found")
        return False
    return api.set_group_state(group["id"], state)


def ok(ctx, entity_name, action, bridge=None):
    """Print standardized success message (unless --quiet)."""
    if ctx.get("quiet"):
        return
    suffix = f"  ({bridge})" if bridge else ""
    print(f"OK: {entity_name} -> {action}{suffix}")


def add_transition(state, transition):
    """Add transition time to state dict if specified."""
    if transition:
        state["transitiontime"] = int(float(transition) * 10)
    return state


def fail(msg=None):
    """Print optional error and exit with error code."""
    if msg:
        err(msg)
    sys.exit(1)


# --- Light Commands ---

def cmd_light_on(ctx, args):
    """Turn on a light."""
    if not args:
        fail("Usage: on <light_name>")
    name = " ".join(args)
    light = resolve(name, get_all(ctx, "get_lights"), "light")
    if not light:
        fail()
    state = add_transition({"on": True}, ctx.get("transition"))
    if set_light(ctx, light, state):
        ok(ctx, light["name"], "ON", light["bridge"])
    else:
        fail()


def cmd_light_off(ctx, args):
    """Turn off a light."""
    if not args:
        fail("Usage: off <light_name>")
    name = " ".join(args)
    light = resolve(name, get_all(ctx, "get_lights"), "light")
    if not light:
        fail()
    state = add_transition({"on": False}, ctx.get("transition"))
    if set_light(ctx, light, state):
        ok(ctx, light["name"], "OFF", light["bridge"])
    else:
        fail()


def cmd_light_toggle(ctx, args):
    """Toggle a light on/off."""
    if not args:
        fail("Usage: toggle <light_name>")
    name = " ".join(args)
    light = resolve(name, get_all(ctx, "get_lights"), "light")
    if not light:
        fail()
    new_on = not light["state"]["on"]
    state = add_transition({"on": new_on}, ctx.get("transition"))
    if set_light(ctx, light, state):
        ok(ctx, light["name"], "ON" if new_on else "OFF", light["bridge"])
    else:
        fail()


def cmd_brightness(ctx, args):
    """Set light brightness (0-254)."""
    if len(args) < 2:
        fail("Usage: brightness <light_name> <0-254>")
    try:
        bri_raw = int(args[-1])
    except ValueError:
        fail("Brightness must be an integer (0-254)")
    if bri_raw < 0 or bri_raw > 254:
        fail(f"Brightness {bri_raw} out of range (must be 0-254)")
    name = " ".join(args[:-1])
    light = resolve(name, get_all(ctx, "get_lights"), "light")
    if not light:
        fail()
    state = add_transition({"on": True, "bri": bri_raw}, ctx.get("transition"))
    if set_light(ctx, light, state):
        ok(ctx, light["name"], f"brightness {bri_raw}", light["bridge"])
    else:
        fail()


def cmd_color(ctx, args):
    """Set light color (hue 0-65535, sat 0-254)."""
    if len(args) < 3:
        fail("Usage: color <light_name> <hue 0-65535> <sat 0-254>")
    try:
        hue_raw = int(args[-2])
        sat_raw = int(args[-1])
    except ValueError:
        fail("Hue and saturation must be integers")
    if hue_raw < 0 or hue_raw > 65535:
        fail(f"Hue {hue_raw} out of range (must be 0-65535)")
    if sat_raw < 0 or sat_raw > 254:
        fail(f"Saturation {sat_raw} out of range (must be 0-254)")
    name = " ".join(args[:-2])
    light = resolve(name, get_all(ctx, "get_lights"), "light")
    if not light:
        fail()
    state = add_transition({"on": True, "hue": hue_raw, "sat": sat_raw}, ctx.get("transition"))
    if set_light(ctx, light, state):
        ok(ctx, light["name"], f"hue={hue_raw} sat={sat_raw}", light["bridge"])
    else:
        fail()


def cmd_temp(ctx, args):
    """Set color temperature (153=cool, 500=warm)."""
    if len(args) < 2:
        fail("Usage: temp <light_name> <153-500>")
    try:
        ct_raw = int(args[-1])
    except ValueError:
        fail("Color temp must be an integer (153-500 mireds)")
    if ct_raw < 153 or ct_raw > 500:
        fail(f"Color temp {ct_raw} out of range (153=cool/blue, 500=warm/yellow)")
    name = " ".join(args[:-1])
    light = resolve(name, get_all(ctx, "get_lights"), "light")
    if not light:
        fail()
    state = add_transition({"on": True, "ct": ct_raw}, ctx.get("transition"))
    if set_light(ctx, light, state):
        ok(ctx, light["name"], f"ct={ct_raw}", light["bridge"])
    else:
        fail()


def cmd_alert(ctx, args):
    """Flash a light once or for 15 seconds."""
    if not args:
        fail("Usage: alert <light_name> [long]")
    mode = "lselect" if (len(args) >= 2 and args[-1] == "long") else "select"
    name_parts = args if mode == "select" else args[:-1]
    name = " ".join(name_parts)
    light = resolve(name, get_all(ctx, "get_lights"), "light")
    if not light:
        fail()
    if set_light(ctx, light, {"alert": mode}):
        duration = "15 seconds" if mode == "lselect" else "once"
        ok(ctx, light["name"], f"alert ({duration})", light["bridge"])
    else:
        fail()


# --- Room/Group Commands ---

def cmd_room(ctx, args):
    """Room subcommand dispatcher."""
    if not args:
        fail("Usage: room <list|on|off|blink> [room_name]")

    subcmd = args[0].lower()
    sub_args = args[1:]

    room_cmds = {"list": cmd_room_list, "on": lambda c, a: cmd_room_onoff(c, a, on=True),
                 "off": lambda c, a: cmd_room_onoff(c, a, on=False), "blink": cmd_room_blink}
    handler = room_cmds.get(subcmd)
    if handler:
        handler(ctx, sub_args)
    else:
        fail(f"Unknown room command: {subcmd}. Available: list, on, off, blink")


def cmd_room_list(ctx, _args=None):
    """List all rooms/groups."""
    all_groups = get_all(ctx, "get_groups")
    if ctx.get("as_json"):
        print(json.dumps(all_groups, indent=2))
    else:
        print(format_room_list(all_groups, ctx["bridges"]))


def cmd_room_onoff(ctx, args, on=True):
    """Turn room on or off."""
    if not args:
        action = "on" if on else "off"
        fail(f"Usage: room {action} <room_name>")
    room_name = " ".join(args)
    group = resolve(room_name, get_all(ctx, "get_groups"), "room")
    if not group:
        fail()
    state = add_transition({"on": on}, ctx.get("transition"))
    action = "ON" if on else "OFF"
    if set_group(ctx, group, state):
        ok(ctx, group["name"], action, group["bridge"])
    else:
        fail()


def cmd_room_blink(ctx, args):
    """Blink a room (off, wait, on)."""
    if not args:
        fail("Usage: room blink <room_name> [delay_seconds]")
    room_name = " ".join(args)
    delay = 1.0
    # Check if last arg is a number (delay)
    parts = room_name.rsplit(" ", 1)
    if len(parts) == 2:
        try:
            delay = float(parts[1])
            room_name = parts[0]
        except ValueError:
            pass
    group = resolve(room_name, get_all(ctx, "get_groups"), "room")
    if not group:
        fail()
    if not ctx.get("quiet"):
        print(f"Blinking {group['name']}...")
    set_group(ctx, group, {"on": False})
    time.sleep(delay)
    set_group(ctx, group, {"on": True})
    ok(ctx, group["name"], "blinked", group["bridge"])


# --- Scene Commands ---

def cmd_scenes(ctx, args):
    """List all scenes."""
    # Allow positional bridge filter: scenes alpha
    bf_override = args[0] if args else None
    if bf_override:
        ctx = {**ctx, "bridge_filter": bf_override}
    all_scenes = get_all(ctx, "get_scenes")
    all_groups = get_all(ctx, "get_groups")
    if ctx.get("as_json"):
        print(json.dumps(all_scenes, indent=2))
    else:
        print(format_scene_list(all_scenes, all_groups, ctx["bridges"]))


def cmd_scene(ctx, args):
    """Activate a scene by name."""
    if not args:
        fail("Usage: scene <scene_name>")
    scene_name = " ".join(args)
    all_scenes = get_all(ctx, "get_scenes")
    scene = resolve(scene_name, all_scenes, "scene")
    if not scene:
        fail()
    api = ctx["apis"].get(scene["bridge"])
    if api and api.activate_scene(scene["id"], scene.get("group", "0")):
        ok(ctx, f"scene '{scene['name']}'", "activated", scene["bridge"])
    else:
        fail("Scene activation failed")


# --- List Command ---

def cmd_list(ctx, args):
    """List all lights."""
    # Allow positional bridge filter: list alpha
    bf_override = args[0] if args else None
    if bf_override:
        ctx = {**ctx, "bridge_filter": bf_override}
    all_lights = get_all(ctx, "get_lights")
    if ctx.get("as_json"):
        print(json.dumps(all_lights, indent=2))
    else:
        print(format_light_list(all_lights, ctx["bridges"]))


# --- Bridge/Discovery Commands ---

def cmd_bridges(ctx, _args):
    """Show configured bridges and their connectivity."""
    apis = ctx["apis"]
    bridges = ctx["bridges"]

    if not apis:
        print("No bridges configured in ~/.hue/")
        print("Run 'control.py discover' to find bridges on your network.")
        return

    if ctx.get("as_json"):
        result = {}
        for key in sorted(apis.keys()):
            api = apis[key]
            info = api.get_config()
            result[key] = {
                "name": api.bridge_name, "ip": api.ip, "id": api.bridge_id,
                "online": info is not None and isinstance(info, dict) and "swversion" in info,
                "config": bridges[key].get("_config_file", "?"),
            }
            if result[key]["online"]:
                result[key].update({
                    "sw": info.get("swversion"), "api": info.get("apiversion"),
                    "zigbee": info.get("zigbeechannel"), "lights": api.get_light_count()
                })
        print(json.dumps(result, indent=2))
    else:
        for key in sorted(apis.keys()):
            api = apis[key]
            config_file = bridges[key].get("_config_file", "?")
            info = api.get_config()
            print(format_bridge_status(api, config_file, info))


def cmd_discover(ctx, _args):
    """Discover bridges on the network."""
    print("Discovering Hue bridges on network...")
    found = discover_bridges()

    for b in found:
        ip = b.get("internalipaddress", "?")
        config = get_bridge_config(ip)
        b["_name"] = config.get("name", "Unknown") if config else "Unknown"

    known_ips = {c["bridge_ip"] for c in ctx["bridges"].values()}
    print(format_discovery(found, known_ips))


def cmd_pair(ctx, args):
    """Pair with a new bridge."""
    if not args:
        print("Usage: pair <bridge_ip>")
        fail()
    ip = args[0]
    print(f"Attempting to pair with bridge at {ip}...")
    print("Make sure you've pressed the bridge button within the last 30 seconds.")
    pair_bridge(ip)


def cmd_status(ctx, _args):
    """Full health check — bridges + discovery."""
    print("=== Hue System Status ===\n")
    cmd_bridges(ctx, [])

    print("\n--- Network Discovery ---")
    try:
        discovered = discover_bridges()
        known_ips = {c["bridge_ip"] for c in ctx["bridges"].values()}
        print(format_status_discovery(discovered, known_ips))
    except Exception as e:
        print(f"  Discovery failed: {e}")


# --- Command dispatch table ---

COMMANDS = {
    # Light commands
    "on":         cmd_light_on,
    "off":        cmd_light_off,
    "toggle":     cmd_light_toggle,
    "brightness": cmd_brightness,
    "bri":        cmd_brightness,       # alias
    "color":      cmd_color,
    "temp":       cmd_temp,
    "ct":         cmd_temp,             # alias
    "alert":      cmd_alert,
    # Room commands
    "room":       cmd_room,
    # Scene commands
    "scenes":     cmd_scenes,
    "scene":      cmd_scene,
    # List
    "list":       cmd_list,
    "ls":         cmd_list,             # alias
    # Bridge management
    "bridges":    cmd_bridges,
    "discover":   cmd_discover,
    "pair":       cmd_pair,
    "status":     cmd_status,
}
