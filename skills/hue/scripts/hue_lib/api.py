"""Hue Bridge API client with rate limiting."""

import json
import sys
import time
import urllib.request
import urllib.error
import socket
import threading


class RateLimiter:
    """Simple per-bridge rate limiter. 10 req/sec for lights, 1 req/sec for groups."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_light_call = {}   # bridge_key -> timestamp
        self._last_group_call = {}   # bridge_key -> timestamp
        self._light_interval = 0.1   # 10 req/sec
        self._group_interval = 1.0   # 1 req/sec

    def wait_for_light(self, bridge_key):
        """Wait if needed before a light API call."""
        with self._lock:
            now = time.monotonic()
            last = self._last_light_call.get(bridge_key, 0)
            wait = self._light_interval - (now - last)
            if wait > 0:
                time.sleep(wait)
            self._last_light_call[bridge_key] = time.monotonic()

    def wait_for_group(self, bridge_key):
        """Wait if needed before a group API call."""
        with self._lock:
            now = time.monotonic()
            last = self._last_group_call.get(bridge_key, 0)
            wait = self._group_interval - (now - last)
            if wait > 0:
                time.sleep(wait)
            self._last_group_call[bridge_key] = time.monotonic()


# Global rate limiter instance
_rate_limiter = RateLimiter()


# Common Hue API error codes → human-readable messages
HUE_ERRORS = {
    1: "Unauthorized — re-pair the bridge",
    2: "Invalid JSON body",
    3: "Resource not found",
    4: "Method not allowed",
    5: "Missing required parameter",
    6: "Parameter not available",
    7: "Invalid parameter value",
    8: "Parameter is read-only",
    11: "Too many items in list",
    12: "Portal connection required",
    101: "Link button not pressed — press it and retry within 30s",
    201: "Parameter not modifiable (light may be off or unreachable)",
    301: "Group table full",
    302: "Light already in group",
    304: "Scene table full (delete old scenes first)",
    305: "Scene table full (delete old scenes first)",
    401: "Scene creation in progress — wait and retry",
    501: "Bridge internal error",
    502: "Bridge internal error",
    901: "Bridge internal error (swupdate)",
}


def translate_hue_error(error_obj):
    """Translate a Hue API error dict to a readable message."""
    etype = error_obj.get("type", 0)
    description = error_obj.get("description", "Unknown error")
    human = HUE_ERRORS.get(etype)
    if human:
        return f"{human} (error {etype})"
    return description


class HueAPI:
    """API client for a single Hue bridge."""

    def __init__(self, bridge_key, config):
        self.bridge_key = bridge_key
        self.ip = config["bridge_ip"]
        self.username = config["username"]
        self.bridge_name = config.get("bridge_name", bridge_key)
        self.bridge_id = config.get("bridge_id", "?")
        self.config = config

    def _request(self, path, method="GET", data=None, timeout=5, retries=2):
        """Make an API request with error handling and retry.

        Args:
            retries: Number of retry attempts for transient failures (default: 2).
        """
        url = f"http://{self.ip}/api/{self.username}{path}"
        last_error = None

        for attempt in range(1 + retries):
            req = urllib.request.Request(url, method=method)
            req.add_header('Content-Type', 'application/json')
            if data is not None:
                req.data = json.dumps(data).encode()

            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    return json.loads(response.read())
            except socket.timeout:
                last_error = f"TIMEOUT: {self.bridge_key} ({self.ip})"
            except urllib.error.URLError as e:
                last_error = f"OFFLINE: {self.bridge_key} ({self.ip}) — {e.reason}"
            except Exception as e:
                last_error = f"ERROR: {self.bridge_key}: {e}"

            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))  # backoff: 0.5s, 1.0s, ...

        print(last_error, file=sys.stderr)
        if "TIMEOUT" in last_error or "OFFLINE" in last_error:
            print(f"  Hint: Check if bridge IP changed with 'control.py discover'", file=sys.stderr)
        return None

    def _check_auth_error(self, result):
        """Check if result is an auth error. Returns True if error."""
        if isinstance(result, list) and result and isinstance(result[0], dict) and "error" in result[0]:
            msg = translate_hue_error(result[0]["error"])
            print(f"AUTH ERROR on {self.bridge_key}: {msg}", file=sys.stderr)
            etype = result[0]["error"].get("type", 0)
            if etype in (1, 101):
                print(f"  Hint: Re-pair with 'control.py pair {self.ip}'", file=sys.stderr)
            return True
        return False

    # --- Lights ---

    def get_lights(self):
        """Get all lights from this bridge."""
        result = self._request("/lights")
        if result is None or self._check_auth_error(result):
            return {}
        lights = {}
        for light_id, light in result.items():
            lights[f"{self.bridge_key}:{light_id}"] = {
                "id": light_id,
                "name": light["name"],
                "bridge": self.bridge_key,
                "bridge_ip": self.ip,
                "username": self.username,
                "state": light["state"],
                "type": light.get("type", ""),
                "modelid": light.get("modelid", ""),
                "productname": light.get("productname", ""),
                "manufacturername": light.get("manufacturername", ""),
                "swversion": light.get("swversion", ""),
            }
        return lights

    def set_light_state(self, light_id, state):
        """Set state of a light. Returns True on success."""
        _rate_limiter.wait_for_light(self.bridge_key)
        result = self._request(f"/lights/{light_id}/state", method="PUT", data=state)
        if result is None:
            return False
        errors = [translate_hue_error(r["error"]) for r in result if isinstance(r, dict) and "error" in r]
        if errors:
            print(f"ERROR: {'; '.join(errors)}", file=sys.stderr)
            return False
        return True

    # --- Groups ---

    def get_groups(self):
        """Get all groups from this bridge."""
        result = self._request("/groups")
        if result is None or self._check_auth_error(result):
            return {}
        groups = {}
        for group_id, group in result.items():
            groups[f"{self.bridge_key}:{group_id}"] = {
                "id": group_id,
                "name": group["name"],
                "type": group.get("type", ""),
                "class": group.get("class", ""),
                "lights": group.get("lights", []),
                "all_on": group.get("state", {}).get("all_on", False),
                "any_on": group.get("state", {}).get("any_on", False),
                "bridge": self.bridge_key,
                "bridge_ip": self.ip,
                "username": self.username,
            }
        return groups

    def set_group_state(self, group_id, state):
        """Set state for a group/room. Returns True on success."""
        _rate_limiter.wait_for_group(self.bridge_key)
        result = self._request(f"/groups/{group_id}/action", method="PUT", data=state)
        if result is None:
            return False
        errors = [translate_hue_error(r["error"]) for r in result if isinstance(r, dict) and "error" in r]
        if errors:
            print(f"ERROR: {'; '.join(errors)}", file=sys.stderr)
            return False
        return True

    # --- Scenes ---

    def get_scenes(self):
        """Get all scenes from this bridge."""
        result = self._request("/scenes")
        if result is None or isinstance(result, list):
            return {}
        scenes = {}
        for scene_id, scene in result.items():
            scenes[f"{self.bridge_key}:{scene_id}"] = {
                "id": scene_id,
                "name": scene.get("name", ""),
                "type": scene.get("type", ""),
                "group": scene.get("group", ""),
                "lights": scene.get("lights", []),
                "bridge": self.bridge_key,
                "bridge_ip": self.ip,
                "username": self.username,
            }
        return scenes

    def activate_scene(self, scene_id, group_id="0"):
        """Activate a scene via its group."""
        _rate_limiter.wait_for_group(self.bridge_key)
        result = self._request(f"/groups/{group_id}/action", method="PUT", data={"scene": scene_id})
        if result is None:
            return False
        return not any(isinstance(r, dict) and "error" in r for r in result)

    # --- Bridge Info ---

    def get_config(self):
        """Get bridge configuration."""
        return self._request("/config")

    def get_light_count(self):
        """Get number of lights on this bridge."""
        lights = self._request("/lights")
        if lights and isinstance(lights, dict):
            return len(lights)
        return 0

    def is_online(self):
        """Check if bridge is reachable and authenticated."""
        config = self.get_config()
        return config is not None and isinstance(config, dict) and "swversion" in config
