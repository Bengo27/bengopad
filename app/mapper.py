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
        # minigame mode: sticks pushed to the edge, mouse rotates them
        self.minigame = False
        self._ang_r = -90.0   # degrees, -90 = straight up
        self._ang_l = -90.0

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
    def _rmb_minigame(self, name: str) -> bool:
        return (name == "MOUSE_RIGHT" and self.vehicle
                and self.cfg.get("vehicle_rmb_minigame", True))

    def input_down(self, name: str):
        if self.minigame and name == "MOUSE_LEFT":
            # hotwire: hold LMB = the mouse moves L and R together (mirrored)
            with self._lock:
                self._held[name] = ""
                self._ang_r = (180.0 - self._ang_l) % 360
            return
        if self._rmb_minigame(name):
            self.set_minigame(True)
            with self._lock:
                self._held[name] = ""
            return
        with self._lock:
            if name in self._held:
                return  # key auto-repeat
            target = self._resolve(self.layout().get(name, "") or "")
            self._held[name] = target
            self._press(target)

    def input_up(self, name: str):
        if name == "MOUSE_RIGHT" and self.minigame and self._held.get(name) == "":
            with self._lock:
                self._held.pop(name, None)
            self.set_minigame(False)
            return
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
                # The mouse "traces" the circle: only movement along the
                # circle (tangent) turns the stick, so you can follow an arc
                # in any direction (e.g. down the left side for R).
                step = float(self.cfg.get("minigame_deg_per_count", 0.25))
                both = self._held.get("MOUSE_LEFT") == ""
                left = both or self.cfg.get("minigame_left_key") in self._held
                if both:
                    # slide along the arcs: mouse down = both sticks go down
                    a = self._ang_l
                    if a > 180:
                        a -= 360
                    a = max(-90.0, min(90.0, a + dy * step))
                    self._ang_l = a % 360
                    self._ang_r = (180.0 - a) % 360
                    return
                ang = self._ang_l if left else self._ang_r
                rad = math.radians(ang)
                tang = -dx * math.sin(rad) + dy * math.cos(rad)
                if abs(tang) < 1e-9 and (dx or dy):
                    tang = dx if abs(dx) >= abs(dy) else dy
                ang = (ang + tang * step) % 360
                if left:
                    self._ang_l = ang
                    if both:  # R mirrors L (L's arc is on the right, R's on the left)
                        self._ang_r = (180.0 - ang) % 360
                else:
                    self._ang_r = ang
                return
            self._mdx += dx
            self._mdy += dy

    def set_minigame(self, on: bool):
        with self._lock:
            self.minigame = on
            self._ang_r = self._ang_l = -90.0
            self._l_last = time.perf_counter()
            self._mdx = self._mdy = self._rx = self._ry = 0.0

    def _stick_at(self, angle: float) -> tuple:
        tilt = min(max(float(self.cfg.get("minigame_tilt", 1.0)), 0.1), 1.0)
        rad = math.radians(angle)
        return math.cos(rad) * tilt, math.sin(rad) * tilt

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
            self._ang_r = self._ang_l = -90.0
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
        if self.minigame:
            now = time.perf_counter()
            dt = min(now - getattr(self, "_l_last", now), 0.05)
            self._l_last = now
            with self._lock:
                rate = float(self.cfg.get("minigame_key_deg_per_sec", 180))
                # clockwise = S / D (down the right side), counter = W / A
                cw = ("S" in self._held) or ("D" in self._held)
                ccw = ("W" in self._held) or ("A" in self._held)
                if cw and not ccw:
                    self._ang_l = (self._ang_l + rate * dt) % 360
                elif ccw and not cw:
                    self._ang_l = (self._ang_l - rate * dt) % 360
                return self._stick_at(self._ang_l)
        with self._lock:
            x = y = 0
            for target in self._held.values():
                d = STICK_DIRS.get(target)
                if d:
                    x += d[0]
                    y += d[1]
            walk = self.cfg.get("walk_key", "") in self._held
            abs_l = self._stick_at(self._ang_l)
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
                return self._stick_at(self._ang_r)
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
