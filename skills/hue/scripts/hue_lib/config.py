"""Bridge configuration management."""

import json
import os
import glob as glob_mod

CONFIG_DIR = os.path.expanduser("~/.hue")
os.makedirs(CONFIG_DIR, exist_ok=True)


def load_bridges():
    """Dynamically load ALL bridge configs from ~/.hue/*.json."""
    bridges = {}
    for config_path in sorted(glob_mod.glob(os.path.join(CONFIG_DIR, "*.json"))):
        filename = os.path.basename(config_path)
        if filename.startswith("_"):  # skip internal files like _state.json
            continue
        try:
            with open(config_path) as f:
                config = json.load(f)
                # Use bridge_name from config if available, else derive from filename
                bridge_key = config.get("bridge_name", filename.replace(".json", "")).lower()
                config["_config_file"] = config_path
                bridges[bridge_key] = config
        except (json.JSONDecodeError, IOError) as e:
            import sys
            print(f"WARNING: Failed to load {config_path}: {e}", file=sys.stderr)
    return bridges
