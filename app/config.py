"""Settings file: %APPDATA%\\BengoPad\\config.json"""
import copy
import json
import os

LAYOUT_VERSION = 2

# Based on GTA 5 PC keys -> PlayStation buttons
# (in GTA 6 pick the "Classic" control scheme, which works like GTA 5)
DEFAULTS = {
    "layout_version": LAYOUT_VERSION,
    "host": "",
    "user": "",
    "toggle_key": "F8",        # capture on/off (always works)
    "vehicle_key": "F9",       # switch on-foot / vehicle layout
    "walk_key": "",            # hold = left stick at half speed ("" = off)
    "mouse": {
        "sensitivity": 1.0,    # overall speed
        "curve": 0.85,         # <1 = faster small movements, >1 = more precise
        "anti_deadzone": 0.18, # skips the game's own stick deadzone
        "smoothing": 0.45,     # 0 = raw, 0.9 = very smooth
        "invert_y": False,
    },
    "on_foot": {
        "W": "LS_UP", "S": "LS_DOWN", "A": "LS_LEFT", "D": "LS_RIGHT",
        "MOUSE_LEFT": "R2",        # shoot
        "MOUSE_RIGHT": "L2",       # aim
        "LSHIFT": "CROSS",         # sprint
        "SPACE": "SQUARE",         # jump
        "F": "TRIANGLE",           # enter vehicle
        "R": "CIRCLE",             # reload / melee
        "Q": "R1",                 # cover
        "TAB": "L1",               # weapon wheel
        "LCTRL": "L3",             # stealth / crouch
        "C": "R3",                 # look behind
        "CAPSLOCK": "L3+R3",       # special ability
        "V": "SHARE",              # change camera
        "M": "TOUCHPAD",           # map
        "ESC": "OPTIONS", "P": "OPTIONS",  # pause
        "UP": "UP", "DOWN": "DOWN", "LEFT": "LEFT", "RIGHT": "RIGHT",
        "LALT": "DOWN",            # character wheel / minimap (hold)
        "WHEEL_UP": "LEFT",        # previous weapon
        "WHEEL_DOWN": "RIGHT",     # next weapon
        "E": "", "G": "", "X": "", "Z": "", "MOUSE_MIDDLE": "",
    },
    # Only the keys listed here change in vehicle mode; the rest come from on_foot
    "vehicle": {
        "W": "R2",                 # gas
        "S": "L2",                 # brake / reverse
        "A": "LS_LEFT", "D": "LS_RIGHT",
        "SPACE": "R1",             # handbrake
        "E": "L3",                 # horn
        "H": "RIGHT",              # headlights
        "Q": "LEFT",               # radio
        "MOUSE_RIGHT": "L1",       # drive-by aim
        "MOUSE_LEFT": "R1",        # drive-by shoot (with aim held)
        "LSHIFT": "", "WHEEL_UP": "", "WHEEL_DOWN": "",
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
                user = json.load(f)
            if user.get("layout_version") != LAYOUT_VERSION:
                # new default layout: keep connection + mouse settings only
                user = {k: user[k] for k in ("host", "user", "mouse") if k in user}
                cfg = _merge(DEFAULTS, user)
                save(cfg)
                return cfg
            return _merge(DEFAULTS, user)
        except (OSError, ValueError):
            pass
    cfg = copy.deepcopy(DEFAULTS)
    save(cfg)
    return cfg


def save(cfg: dict):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
