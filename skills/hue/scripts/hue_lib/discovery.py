"""Bridge discovery and pairing."""

import json
import os
import urllib.request

from .config import CONFIG_DIR


def discover_bridges():
    """Discover Hue bridges on the local network via meethue.com N-UPnP."""
    import sys
    url = "https://discovery.meethue.com/"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read())  # [{"id": "...", "internalipaddress": "..."}]
    except Exception as e:
        print(f"N-UPnP discovery failed: {e}", file=sys.stderr)
        return []


def get_bridge_config(ip, username=None):
    """Get bridge configuration (name, model, etc.)."""
    if username:
        url = f"http://{ip}/api/{username}/config"
    else:
        url = f"http://{ip}/api/0/config"  # unauthenticated, limited info
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read())
    except Exception:
        return None


def pair_bridge(ip):
    """Pair with a Hue bridge. User must press the bridge button first."""
    url = f"http://{ip}/api"
    data = json.dumps({"devicetype": "dispatch#pangserve"}).encode()

    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read())

        if result and "error" in result[0]:
            error = result[0]["error"]
            if error["type"] == 101:
                print("ERROR: Link button not pressed. Press the button on the bridge and try again within 30 seconds.")
                return None
            else:
                print(f"ERROR: {error['description']}")
                return None

        if result and "success" in result[0]:
            username = result[0]["success"]["username"]
            config = get_bridge_config(ip, username)
            bridge_name = config.get("name", "unknown") if config else "unknown"
            bridge_id = config.get("bridgeid", "unknown") if config else "unknown"

            safe_name = bridge_name.lower().replace(" ", "_")
            cred_data = {
                "bridge_ip": ip,
                "bridge_name": bridge_name,
                "bridge_id": bridge_id,
                "username": username
            }
            config_path = os.path.join(CONFIG_DIR, f"{safe_name}.json")
            with open(config_path, "w") as f:
                json.dump(cred_data, f, indent=2)

            print(f"OK: Paired with {bridge_name} ({ip})")
            print(f"   Bridge ID: {bridge_id}")
            print(f"   Credentials saved to: {config_path}")
            return cred_data

    except Exception as e:
        print(f"ERROR: Failed to pair: {e}")
        return None
