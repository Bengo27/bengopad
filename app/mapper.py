"""Turns keyboard/mouse input into controller state. Pure logic, no Windows calls."""
import math
import threading
import time

from keys import BUTTONS, STICK_DIRS

WHEEL_TAP_SEC = 0.06


class Mapper:
    def __init__(self, cfg: dict):
        self._lock = threading.Lock()
        self.cfg = cfg
        self.vehicle = False
        self._held = {}            # input name -> target it was mapped to
        self._refs = {}            # button -> how many inputs hold it
        self._events = []          # (button, pressed) waiting to be sent
        self._taps = []            # (release_time, button)
        self._mdx = 0.0
        self._mdy = 0.0
        self._rx = 0.0
        self._ry = 0.0
        # minigame mode: the mouse places the sticks and they stay there
        self.minigame = False
        self._abs_r = [0.0, 0.0]
        self._abs_l = [0.0, 0.0]

    # ---------- layout ----------
    def layout(self) -> dict:
        lay = dict(self.cfg["on_foot"])
        if self.vehicle:
            lay.update(self.cfg.get("vehicle", {}))
        return lay

    def _resolve(self, target: str) -> str:
        """ATTACK = R2 (shoot) while aiming, otherwise Square (punch / melee)."""
        if target == "ATTACK":
            aiming = any(t == "L2" for n, t in self._held.items() if n == "MOUSE_RIGHT")
            return "R2" if aiming else "SQUARE"
        return target

    def _press(self, target: str):
        if "+" in target:  # combo like "L3+R3"
            for part in target.split("+"):
                self._press(part.strip())
            return
        if target in BUTTONS:
            n = self._refs.get(target, 0)
            self._refs[target] = n + 1
            if n == 0:
                self._events.append((target, True))

    def _release(self, target: str):
        if "+" in target:
            for part in target.split("+"):
                self._release(part.strip())
            return
        if target in BUTTONS:
            n = self._refs.get(target, 0)
            if n <= 1:
                self._refs.pop(target, None)
                if n == 1:
                    self._events.append((target, False))
            else:
                self._refs[target] = n - 1

    # ---------- input from hooks ----------
    def input_down(self, name: str):
        with self._lock:
            if name in self._held:
                return  # key auto-repeat
            target = self._resolve(self.layout().get(name, "") or "")
            self._held[name] = target
            self._press(target)

    def input_up(self, name: str):
        with self._lock:
            target = self._held.pop(name, None)
            if target:
                self._release(target)

    def wheel(self, name: str):
        with self._lock:
            target = self.layout().get(name, "")
            if target in BUTTONS and target not in self._refs:
                self._press(target)
                self._taps.append((time.perf_counter() + WHEEL_TAP_SEC, target))

    def add_mouse(self, dx: float, dy: float):
        with self._lock:
            if self.minigame:
                rng = max(float(self.cfg.get("minigame_range", 300)), 20.0)
                left = self.cfg.get("minigame_left_key") in self._held
                pos = self._abs_l if left else self._abs_r
                pos[0] += dx / rng
                pos[1] += dy / rng
                mag = math.hypot(*pos)
                if mag > 1.0:
                    pos[0] /= mag
                    pos[1] /= mag
                return
            self._mdx += dx
            self._mdy += dy

    def set_minigame(self, on: bool):
        with self._lock:
            self.minigame = on
            self._abs_r = [0.0, 0.0]
            self._abs_l = [0.0, 0.0]
            self._mdx = self._mdy = self._rx = self._ry = 0.0

    def center_sticks(self):
        with self._lock:
            self._abs_r = [0.0, 0.0]
            self._abs_l = [0.0, 0.0]

    def set_vehicle(self, on: bool):
        with self._lock:
            if on == self.vehicle:
                return
            self.vehicle = on
            lay = self.layout()
            for name, old in list(self._held.items()):
                new = self._resolve(lay.get(name, "") or "")
                if new != old:
                    self._release(old)
                    self._held[name] = new
                    self._press(new)

    def release_all(self):
        with self._lock:
            for target in self._held.values():
                self._release(target)
            for _t, target in self._taps:
                self._release(target)
            self._held.clear()
            self._taps.clear()
            self._abs_r = [0.0, 0.0]
            self._abs_l = [0.0, 0.0]
            self._mdx = self._mdy = 0.0
            self._rx = self._ry = 0.0

    # ---------- output, called by the sender thread ----------
    def take_events(self) -> list:
        with self._lock:
            now = time.perf_counter()
            keep = []
            for when, target in self._taps:
                if when <= now:
                    self._release(target)
                else:
                    keep.append((when, target))
            self._taps = keep
            events, self._events = self._events, []
            return events

    def left_stick(self) -> tuple:
        with self._lock:
            x = y = 0
            for target in self._held.values():
                d = STICK_DIRS.get(target)
                if d:
                    x += d[0]
                    y += d[1]
            walk = self.cfg.get("walk_key", "") in self._held
            abs_l = tuple(self._abs_l)
        x = max(-1, min(1, x))
        y = max(-1, min(1, y))
        if x == 0 and y == 0:
            return abs_l if self.minigame else (0.0, 0.0)
        mag = 0.5 if walk else 1.0
        norm = math.hypot(x, y)
        return x / norm * mag, y / norm * mag

    def right_stick(self, dt: float) -> tuple:
        """Mouse speed -> right stick position."""
        m = self.cfg["mouse"]
        if self.minigame:
            with self._lock:
                return tuple(self._abs_r)
        with self._lock:
            dx, dy = self._mdx, self._mdy
            self._mdx = self._mdy = 0.0
        dt = max(dt, 1e-4)
        k = 0.0006 * float(m.get("sensitivity", 1.0))
        tx, ty = dx / dt * k, dy / dt * k
        if m.get("invert_y"):
            ty = -ty
        tmag = math.hypot(tx, ty)
        if tmag > 1.0:  # beyond full tilt - clamp so the stick stops quickly
            tx, ty = tx / tmag, ty / tmag
        a = min(max(float(m.get("smoothing", 0.45)), 0.0), 0.95)
        self._rx = a * self._rx + (1 - a) * tx
        self._ry = a * self._ry + (1 - a) * ty
        mag = math.hypot(self._rx, self._ry)
        if mag < 0.01:
            if tx == 0 and ty == 0:
                self._rx = self._ry = 0.0
            return 0.0, 0.0
        curve = max(float(m.get("curve", 0.85)), 0.1)
        adz = min(max(float(m.get("anti_deadzone", 0.18)), 0.0), 0.9)
        out = adz + (1 - adz) * min(mag, 1.0) ** curve
        return self._rx / mag * out, self._ry / mag * out
