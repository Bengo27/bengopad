"""Windows low-level keyboard/mouse hooks.

While capture is on, all keyboard and mouse input is swallowed (so Veyra or any
other window does not react) and passed to the mapper instead. The cursor stays
locked in the middle of the screen; each mouse move is measured from there.
"""
import ctypes
import threading
from ctypes import wintypes

from keys import VK, VK_NAME

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_MOUSEMOVE = 0x200
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x201, 0x202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x204, 0x205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x207, 0x208
WM_MOUSEWHEEL = 0x20A
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x20B, 0x20C
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

MOUSE_BTN = {
    WM_LBUTTONDOWN: ("MOUSE_LEFT", True), WM_LBUTTONUP: ("MOUSE_LEFT", False),
    WM_RBUTTONDOWN: ("MOUSE_RIGHT", True), WM_RBUTTONUP: ("MOUSE_RIGHT", False),
    WM_MBUTTONDOWN: ("MOUSE_MIDDLE", True), WM_MBUTTONUP: ("MOUSE_MIDDLE", False),
}


class InputHooks:
    def __init__(self, mapper, on_toggle, on_vehicle, cfg, on_minigame=None):
        self.on_minigame = on_minigame
        self.mapper = mapper
        self.on_toggle = on_toggle
        self.on_vehicle = on_vehicle
        self.cfg = cfg
        self.capturing = False
        self._down = set()
        self._center = (0, 0)
        self._thread = None
        self._tid = 0
        self._kb_proc = HOOKPROC(self._kb)
        self._ms_proc = HOOKPROC(self._ms)

    # ---------- public ----------
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    def set_capture(self, on: bool):
        if on:
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            self._center = (w // 2, h // 2)
            user32.SetCursorPos(*self._center)
        else:
            self.mapper.release_all()
        self.capturing = on

    # ---------- hook thread ----------
    def _run(self):
        self._tid = kernel32.GetCurrentThreadId()
        mod = kernel32.GetModuleHandleW(None)
        kb = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, mod, 0)
        ms = user32.SetWindowsHookExW(WH_MOUSE_LL, self._ms_proc, mod, 0)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(kb)
        user32.UnhookWindowsHookEx(ms)

    def _kb(self, code, wparam, lparam):
        if code != 0:
            return user32.CallNextHookEx(None, code, wparam, lparam)
        info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if info.flags & LLKHF_INJECTED:
            return user32.CallNextHookEx(None, code, wparam, lparam)
        vk = info.vkCode
        down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
        repeat = down and vk in self._down
        if down:
            self._down.add(vk)
        else:
            self._down.discard(vk)

        if vk == VK.get(self.cfg["toggle_key"]):
            if down and not repeat:
                self.on_toggle()
            return 1
        if not self.capturing:
            return user32.CallNextHookEx(None, code, wparam, lparam)
        if vk == VK.get(self.cfg["vehicle_key"]):
            if down and not repeat:
                self.on_vehicle()
            return 1
        if vk == VK.get(self.cfg.get("minigame_key", "")):
            if not repeat and self.on_minigame:
                self.on_minigame(down)   # held = minigame, released = normal
            return 1
        name = VK_NAME.get(vk)
        if name:
            if down:
                self.mapper.input_down(name)
                if not repeat and name == self.cfg.get("auto_vehicle_key"):
                    self.on_vehicle()
            else:
                self.mapper.input_up(name)
        return 1

    def _ms(self, code, wparam, lparam):
        if code != 0 or not self.capturing:
            return user32.CallNextHookEx(None, code, wparam, lparam)
        info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        if info.flags & LLMHF_INJECTED:
            return user32.CallNextHookEx(None, code, wparam, lparam)
        if wparam == WM_MOUSEMOVE:
            self.mapper.add_mouse(info.pt.x - self._center[0], info.pt.y - self._center[1])
        elif wparam in MOUSE_BTN:
            name, down = MOUSE_BTN[wparam]
            (self.mapper.input_down if down else self.mapper.input_up)(name)
        elif wparam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            name = "MOUSE_X1" if (info.mouseData >> 16) == 1 else "MOUSE_X2"
            (self.mapper.input_down if wparam == WM_XBUTTONDOWN else self.mapper.input_up)(name)
        elif wparam == WM_MOUSEWHEEL:
            delta = ctypes.c_short(info.mouseData >> 16).value
            self.mapper.wheel("WHEEL_UP" if delta > 0 else "WHEEL_DOWN")
        return 1
