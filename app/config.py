"""Settings file: %APPDATA%\\BengoPad\\config.json"""
import copy
import json
import os

DEFAULTS = {
    "host": "",
    "user": "",
    "toggle_key": "F8",        # capture on/off (always works)
    "vehicle_key": "F9",       # switch on-foot / vehicle layout
    "walk_key": "LALT",        # hold = left stick at half speed
    "mouse": {
        "sensitivity": 1.0,    # overall speed
        "curve": 0.85,         # <1 = faster small movements, >1 = more precise
        "anti_deadzone": 0.18, # skips the game's own stick deadzone
        "smoothing": 0.45,     # 0 = raw, 0.9 = very smooth
        "invert_y": False,
    },
    "on_foot": {
        "W": "LS_UP", "S": "LS_DOWN", "A": "LS_LEFT", "D": "LS_RIGHT",
        "MOUSE_LEFT": "R2", "MOUSE_RIGHT": "L2", "MOUSE_MIDDLE": "R3",
        "SPACE": "SQUARE", "LSHIFT": "CROSS", "F": "TRIANGLE", "R": "CIRCLE",
        "Q": "R1", "TAB": "L1", "LCTRL": "L3", "V": "R3",
        "E": "RIGHT", "G": "LEFT", "X": "DOWN", "Z": "UP",
        "UP": "UP", "DOWN": "DOWN", "LEFT": "LEFT", "RIGHT": "RIGHT",
        "ESC": "OPTIONS", "M": "TOUCHPAD", "F1": "SHARE",
        "WHEEL_UP": "", "WHEEL_DOWN": "",
    },
    # Only the keys listed here change in vehicle mode; the rest come from on_foot
    "vehicle": {
        "W": "R2", "S": "L2", "A": "LS_LEFT", "D": "LS_RIGHT",
        "SPACE": "R1", "MOUSE_LEFT": "", "MOUSE_RIGHT": "",
        "LSHIFT": "CROSS",
    },
}


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "BengoPad")
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in extra.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict) \
                and key not in ("on_foot", "vehicle"):
            out[key] = _merge(out[key], val)
        else:
            out[key] = val
    return out


def load() -> dict:
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return _merge(DEFAULTS, json.load(f))
        except (OSError, ValueError):
            pass
    cfg = copy.deepcopy(DEFAULTS)
    save(cfg)
    return cfg


def save(cfg: dict):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
