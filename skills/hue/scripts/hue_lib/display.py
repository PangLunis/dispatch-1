"""Display formatting for Hue CLI output."""


def format_light_list(all_lights, bridges):
    """Format lights grouped by bridge for terminal display."""
    if not all_lights:
        return "No lights found. Run 'control.py discover' to find bridges, then 'control.py pair <ip>' to authenticate."

    by_bridge = {}
    for key, light in all_lights.items():
        bridge = light["bridge"]
        if bridge not in by_bridge:
            by_bridge[bridge] = []

        state = "ON" if light["state"]["on"] else "OFF"
        reachable = light["state"].get("reachable", None)
        reach_icon = "\u2713" if reachable else "\u2717" if reachable is not None else "?"
        bri = light["state"].get("bri", "")
        ct = light["state"].get("ct", "")
        model = light.get("modelid", "")
        product = light.get("productname", "")

        details = f"[{state}] {reach_icon}"
        if bri:
            details += f"  bri={bri}"
        if ct:
            details += f"  ct={ct}"
        details += f"  model={model}" if model else ""
        details += f"  ({product})" if product else ""

        by_bridge[bridge].append((int(light["id"]), f"  {light['id']:>3}: {light['name']:<40s} {details}"))

    lines = []
    for bridge in sorted(by_bridge.keys()):
        lights = by_bridge[bridge]
        bridge_name = bridges.get(bridge, {}).get("bridge_name", bridge)
        bridge_ip = bridges.get(bridge, {}).get("bridge_ip", "?")
        lines.append(f"\n{bridge_name.upper()} BRIDGE ({bridge_ip}) \u2014 {len(lights)} lights:")
        for _, line in sorted(lights, key=lambda x: x[0]):
            lines.append(line)
    return "\n".join(lines)


def format_room_list(all_groups, bridges):
    """Format rooms/groups grouped by bridge."""
    if not all_groups:
        return "No rooms found."

    by_bridge = {}
    for key, group in all_groups.items():
        bridge = group["bridge"]
        if bridge not in by_bridge:
            by_bridge[bridge] = []
        state = "ALL ON" if group["all_on"] else ("PARTIAL" if group["any_on"] else "OFF")
        by_bridge[bridge].append(
            f"  {group['id']:>3}: {group['name']:<35s} [{state:<8s}] {group['type']:<12s} {len(group['lights'])} lights"
        )

    lines = []
    for bridge in sorted(by_bridge.keys()):
        rooms = by_bridge[bridge]
        bridge_name = bridges.get(bridge, {}).get("bridge_name", bridge)
        lines.append(f"\n{bridge_name.upper()} BRIDGE \u2014 {len(rooms)} rooms/groups:")
        for line in sorted(rooms):
            lines.append(line)
    return "\n".join(lines)


def format_scene_list(all_scenes, all_groups, bridges):
    """Format scenes grouped by bridge."""
    group_names = {}
    for key, g in all_groups.items():
        group_names[f"{g['bridge']}:{g['id']}"] = g["name"]

    by_bridge = {}
    for key, scene in all_scenes.items():
        bridge = scene["bridge"]
        if bridge not in by_bridge:
            by_bridge[bridge] = []
        group_key = f"{bridge}:{scene['group']}"
        room = group_names.get(group_key, f"group {scene['group']}")
        by_bridge[bridge].append(
            f"  {scene['name']:<40s} \u2192 {room:<25s} ({scene['type']}, {len(scene['lights'])} lights)"
        )

    lines = []
    for bridge in sorted(by_bridge.keys()):
        scenes = by_bridge[bridge]
        bridge_name = bridges.get(bridge, {}).get("bridge_name", bridge)
        lines.append(f"\n{bridge_name.upper()} BRIDGE \u2014 {len(scenes)} scenes:")
        for line in sorted(scenes):
            lines.append(line)
    return "\n".join(lines) if lines else "No scenes found."


def format_bridge_status(api, config_file, info):
    """Format a single bridge's status."""
    lines = []
    if info and isinstance(info, dict) and "swversion" in info:
        sw = info.get("swversion", "?")
        apiversion = info.get("apiversion", "?")
        zigbee = info.get("zigbeechannel", "?")
        lc = api.get_light_count()
        status = f"ONLINE  sw={sw}  api={apiversion}  zigbee=ch{zigbee}  lights={lc}"
    else:
        status = "OFFLINE"

    lines.append(f"\n{api.bridge_name} ({api.bridge_key})")
    lines.append(f"  IP: {api.ip}")
    lines.append(f"  ID: {api.bridge_id}")
    lines.append(f"  Config: {config_file}")
    lines.append(f"  Status: {status}")
    return "\n".join(lines)


def format_discovery(bridges, known_ips):
    """Format discovery results."""
    if not bridges:
        return "No bridges found via N-UPnP discovery.\nMake sure bridges are on the same network and have internet access."

    lines = []
    for b in bridges:
        ip = b.get("internalipaddress", "?")
        bid = b.get("id", "?")
        name = b.get("_name", "Unknown")
        paired = "\u2713 paired" if ip in known_ips else "\u2717 NOT paired"

        lines.append(f"\n  {name}")
        lines.append(f"    IP: {ip}")
        lines.append(f"    ID: {bid}")
        lines.append(f"    Status: {paired}")
        if ip not in known_ips:
            lines.append(f"    \u2192 To pair: Press bridge button, then run: control.py pair {ip}")
    return "\n".join(lines)


def format_status_discovery(discovered, known_ips):
    """Format the discovery section of status output."""
    unknown = [b for b in discovered if b.get("internalipaddress") not in known_ips]
    if unknown:
        lines = [f"  Found {len(unknown)} unpaired bridge(s):"]
        for b in unknown:
            lines.append(f"    {b.get('internalipaddress', '?')} (ID: {b.get('id', '?')})")
        return "\n".join(lines)
    return f"  All {len(discovered)} discovered bridges are paired."


def format_match_list(entity_type, name, matches):
    """Format ambiguous match results with disambiguation example."""
    lines = [f"Multiple {entity_type}s match '{name}':"]
    first_name = None
    for item in matches:
        if first_name is None:
            first_name = item["name"]
        if entity_type == "light":
            state = "ON" if item["state"]["on"] else "OFF"
            reach = "\u2713" if item["state"].get("reachable", True) else "\u2717"
            lines.append(f"  - {item['name']} [{state}] {reach}  ({item['bridge']})")
        elif entity_type == "room":
            state = "ALL ON" if item["all_on"] else ("PARTIAL" if item["any_on"] else "OFF")
            lines.append(f"  - {item['name']} ({item['type']}) [{state}] {len(item['lights'])} lights  ({item['bridge']})")
        elif entity_type == "scene":
            lines.append(f"  - {item['name']} ({item['bridge']})")
    # Show actionable example
    if first_name:
        lines.append(f"\nUse the full name to narrow: control.py on \"{first_name}\"")
    bridges = set(item.get("bridge", "") for item in matches)
    if len(bridges) > 1:
        lines.append(f"Or filter by bridge: --bridge {sorted(bridges)[0]}")
    return "\n".join(lines)
