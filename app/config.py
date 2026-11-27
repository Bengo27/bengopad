"""Settings file: %APPDATA%\\BengoPad\\config.json"""
import copy
import json
import os

LAYOUT_VERSION = 8

# GTA 6 "Default" control scheme (RDR2-style) with RDR2 PC keys
DEFAULTS = {
    "layout_version": LAYOUT_VERSION,
    "host": "",
    "user": "",
    "toggle_key": "F8",        # capture on/off (always works)
    "auto_vehicle_key": "F",   # enter/exit vehicle key also switches the layout
    "vehicle_key": "B",        # manual fix if the layout got out of sync
    "walk_key": "",
    # Minigame (hotwiring, slim jim, safes...): while holding this key both sticks
    # are pushed to the edge and moving the mouse left/right ROTATES the right
    # stick around the circle. Add LALT to rotate the LEFT stick instead.
    "minigame_key": "CAPSLOCK",
    "minigame_left_key": "LALT",
    "minigame_deg_per_count": 0.25,  # rotation speed (higher = faster)
    "minigame_tilt": 1.0,            # how far the sticks are pushed (0.1 - 1.0)
    "vehicle_rmb_minigame": True,    # in a car, holding RMB does the same (hotwire)
    "minigame_key_deg_per_sec": 180, # A/D rotate the left stick this fast
    "style": "rdr2",                 # key layout style: "rdr2" or "gta5"
    "mouse": {
        "sensitivity": 1.0,    # overall speed
        "curve": 0.85,         # <1 = faster small movements, >1 = more precise
        "anti_deadzone": 0.18, # skips the game's own stick deadzone
        "smoothing": 0.45,     # 0 = raw, 0.9 = very smooth
        "invert_y": False,
    },
    "on_foot": {
        "W": "LS_UP", "S": "LS_DOWN", "A": "LS_LEFT", "D": "LS_RIGHT",
        "MOUSE_LEFT": "ATTACK",    # punch (Square) / shoot (R2) while aiming
        "MOUSE_RIGHT": "L2",       # aim / interact
        "LSHIFT": "L3",            # run (press again = sprint)
        "SPACE": "CROSS",          # jump / climb
        "E": "TRIANGLE",           # interact (doors, shops, people...)
        "F": "TRIANGLE",           # enter / exit vehicle (also switches layout)
        "LCTRL": "CIRCLE",         # crouch
        "Q": "R1",                 # cover
        "TAB": "L1",               # holster (hold = loadout)
        "C": "R3",                 # look behind (zoom while aiming)
        "M": "TOUCHPAD",           # map
        "ESC": "OPTIONS", "P": "OPTIONS",  # pause
        "UP": "UP",                # phone
        "LEFT": "LEFT",            # radio
        "DOWN": "DOWN",            # objective / minimap
        "RIGHT": "RIGHT",          # detonate explosives
        "V": "SHARE",              # (create button)
        "R": "SQUARE",             # reload / melee
        "MOUSE_MIDDLE": "R1",      # hold = quick throw (grenade)
        "WHEEL_UP": "UP",          # zoom in while aiming
        "WHEEL_DOWN": "DOWN",      # zoom out while aiming
        "G": "", "X": "", "Z": "", "CAPSLOCK": "", "LALT": "",
    },
    # Only the keys listed here change in vehicle mode; everything else stays
    # exactly like on foot, so prompts (slim jim / smash window) and hotwiring
    # work no matter which mode you are in.
    "vehicle": {
        "W": "R2",                 # gas
        "S": "L2",                 # brake / reverse
        "MOUSE_LEFT": "R1",        # shoot
        "Q": "LEFT",               # indicate left (hold = vehicle menu)
        "X": "RIGHT",              # indicate right (hold = partner menu)
        "H": "CIRCLE",             # headlights
        "WHEEL_UP": "", "WHEEL_DOWN": "",  # no phone/minimap while driving
    },
}

STYLE_NAMES = {"rdr2": "RDR2 style", "gta5": "GTA 5 style"}


def style_layout(style: str) -> tuple:
    """Return (on_foot, vehicle) for a style."""
    foot = copy.deepcopy(DEFAULTS["on_foot"])
    veh = copy.deepcopy(DEFAULTS["vehicle"])
    if style == "gta5":
        foot["Z"] = "DOWN"          # radar zoom -> minimap
    return foot, veh


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
                user = {k: user[k] for k in ("host", "user", "mouse", "style") if k in user}
                cfg = _merge(DEFAULTS, user)
                cfg["on_foot"], cfg["vehicle"] = style_layout(cfg.get("style", "rdr2"))
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
