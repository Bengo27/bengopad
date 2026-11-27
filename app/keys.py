"""Key names <-> Windows virtual-key codes, and controller targets."""

VK = {
    "BACKSPACE": 0x08, "TAB": 0x09, "ENTER": 0x0D, "PAUSE": 0x13, "CAPSLOCK": 0x14,
    "ESC": 0x1B, "SPACE": 0x20, "PAGEUP": 0x21, "PAGEDOWN": 0x22, "END": 0x23,
    "HOME": 0x24, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "INSERT": 0x2D, "DELETE": 0x2E,
    "LSHIFT": 0xA0, "RSHIFT": 0xA1, "LCTRL": 0xA2, "RCTRL": 0xA3,
    "LALT": 0xA4, "RALT": 0xA5,
    "SEMICOLON": 0xBA, "EQUALS": 0xBB, "COMMA": 0xBC, "MINUS": 0xBD,
    "PERIOD": 0xBE, "SLASH": 0xBF, "BACKQUOTE": 0xC0, "LBRACKET": 0xDB,
    "BACKSLASH": 0xDC, "RBRACKET": 0xDD, "QUOTE": 0xDE,
}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    VK[_c] = ord(_c)
for _d in range(10):
    VK[str(_d)] = 0x30 + _d
    VK[f"NUM{_d}"] = 0x60 + _d
for _f in range(1, 13):
    VK[f"F{_f}"] = 0x6F + _f

VK_NAME = {code: name for name, code in VK.items()}

# Mouse "keys" used in the mapping
MOUSE_KEYS = ["MOUSE_LEFT", "MOUSE_RIGHT", "MOUSE_MIDDLE", "MOUSE_X1",
              "MOUSE_X2", "WHEEL_UP", "WHEEL_DOWN"]

# Controller buttons understood by Remote Play
BUTTONS = ["UP", "DOWN", "LEFT", "RIGHT", "L1", "R1", "L2", "R2", "CROSS",
           "CIRCLE", "SQUARE", "TRIANGLE", "OPTIONS", "SHARE", "PS", "L3",
           "R3", "TOUCHPAD"]

# Left-stick directions
STICK_DIRS = {"LS_UP": (0, -1), "LS_DOWN": (0, 1), "LS_LEFT": (-1, 0),
              "LS_RIGHT": (1, 0)}

VALID_TARGETS = set(BUTTONS) | set(STICK_DIRS)
