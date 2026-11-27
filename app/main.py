"""Bengo Pad - play PS5 with keyboard & mouse while Veyra (or any capture app) shows the picture."""
import ctypes
import logging
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
from mapper import Mapper  # noqa: E402

APP = "Bengo Pad"
VERSION = "0.5.4"

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # pylint: disable=broad-except
    pass
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:  # pylint: disable=broad-except
    pass

logging.basicConfig(
    filename=os.path.join(config.config_dir(), "log.txt"), filemode="w",
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

import rp  # noqa: E402  (after logging setup)
from hooks import InputHooks  # noqa: E402


def beep(on: bool):
    def _b():
        try:
            import winsound
            winsound.Beep(1200 if on else 500, 80)
        except Exception:  # pylint: disable=broad-except
            pass
    threading.Thread(target=_b, daemon=True).start()


class App:
    def __init__(self):
        self.cfg = config.load()
        self.mapper = Mapper(self.cfg)
        self.ui_q = queue.Queue()
        self.link = rp.Link(self.mapper, lambda s: self.ui_q.put(("status", s)))
        self.hooks = InputHooks(self.mapper, self.toggle_capture, self.toggle_vehicle,
                                self.cfg, self.toggle_minigame)

        self.root = tk.Tk()
        self.root.title(f"{APP} {VERSION}")
        self.root.geometry("500x700")
        self.root.resizable(False, True)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self._build()
        self._fix_clipboard_keys()
        self._start_tray()
        self.hooks.start()
        self.root.after(50, self._poll)
        self._refresh_account()

    # ---------- system tray ----------
    def _start_tray(self):
        self.tray = None
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:  # pylint: disable=broad-except
            logging.exception("tray unavailable")
            return

        def dot(color):
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse((4, 4, 60, 60), fill=color)
            d.text((22, 20), "B", fill="white")
            return img
        self._icons = {True: dot("#0a7d2c"), False: dot("#555555")}
        menu = pystray.Menu(
            pystray.MenuItem("Show Bengo Pad", lambda *_: self.ui_q.put(("call", self.show)), default=True),
            pystray.MenuItem("Quit", lambda *_: self.ui_q.put(("call", self.quit))))
        self.tray = pystray.Icon("BengoPad", self._icons[False], "Bengo Pad - capture OFF", menu)
        self.tray.run_detached()

    def _tray_state(self, on: bool):
        if self.tray:
            self.tray.icon = self._icons[on]
            self.tray.title = f"Bengo Pad - capture {'ON' if on else 'OFF'}"

    def hide(self):
        if self.tray:
            self.root.withdraw()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    # ---------- clipboard (works with Hebrew keyboard layout too) ----------
    def _fix_clipboard_keys(self):
        actions = {86: "<<Paste>>", 67: "<<Copy>>", 88: "<<Cut>>"}

        def on_ctrl(event):
            if event.keysym.lower() in ("v", "c", "x", "a"):
                return None  # English layout - Tk already handles it
            if event.keycode in actions:
                event.widget.event_generate(actions[event.keycode])
                return "break"
            if event.keycode == 65 and hasattr(event.widget, "select_range"):
                event.widget.select_range(0, "end")
                return "break"
            return None

        menu = tk.Menu(self.root, tearoff=0)

        def on_right(event):
            w = event.widget
            menu.delete(0, "end")
            for label, ev in (("Paste", "<<Paste>>"), ("Copy", "<<Copy>>"), ("Cut", "<<Cut>>")):
                menu.add_command(label=label, command=lambda e=ev: w.event_generate(e))
            menu.tk_popup(event.x_root, event.y_root)

        for cls in ("Entry", "TEntry"):
            self.root.bind_class(cls, "<Control-KeyPress>", on_ctrl, add="+")
            self.root.bind_class(cls, "<Button-3>", on_right, add="+")

    # ---------- UI ----------
    def _build(self):
        pad = {"padx": 10, "pady": 4}
        big = ("Segoe UI", 16, "bold")

        self.capture_lbl = tk.Label(self.root, text="CAPTURE OFF", font=big,
                                    fg="white", bg="#444", pady=8)
        self.capture_lbl.pack(fill="x")
        tk.Label(self.root, text=f"{self.cfg['toggle_key']} = capture on/off     "
                 f"{self.cfg.get('auto_vehicle_key')} = enter/exit car (switches layout, "
                 f"{self.cfg['vehicle_key']} = fix)\n"
                 "Hotwire: in a car hold RMB. Move the mouse along R's arc to turn R,\n"
                 f"S/D move L down its arc, W/A move it up.  On foot: hold {self.cfg.get('minigame_key')}\n"
                 "Capture ON hides this window to the tray (click the tray icon to open)",
                 font=("Segoe UI", 9)).pack(**pad)

        box = ttk.LabelFrame(self.root, text="PS5")
        box.pack(fill="x", **pad)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="IP:").pack(side="left", padx=4)
        self.host_var = tk.StringVar(value=self.cfg.get("host", ""))
        ttk.Entry(row, textvariable=self.host_var, width=18).pack(side="left")
        ttk.Button(row, text="Find", command=self.find).pack(side="left", padx=4)
        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=3)
        self.account_lbl = ttk.Label(row2, text="PSN account: -")
        self.account_lbl.pack(side="left", padx=4)
        ttk.Button(row2, text="Link account...", command=self.link_wizard).pack(side="right", padx=4)
        row3 = ttk.Frame(box)
        row3.pack(fill="x", pady=3)
        self.connect_btn = ttk.Button(row3, text="Connect", command=self.connect)
        self.connect_btn.pack(side="left", padx=4)
        ttk.Button(row3, text="Disconnect", command=self.link.disconnect).pack(side="left")
        self.status_lbl = ttk.Label(box, text="Not connected", foreground="#a00")
        self.status_lbl.pack(anchor="w", padx=4, pady=3)

        mbox = ttk.LabelFrame(self.root, text="Mouse -> right stick")
        mbox.pack(fill="x", **pad)
        self.sliders = {}
        self._slider_lbls = {}
        for key, label, lo, hi in [("sensitivity", "Sensitivity", 0.2, 5.0),
                                   ("curve", "Curve (low = snappy)", 0.4, 2.0),
                                   ("anti_deadzone", "Anti-deadzone", 0.0, 0.4),
                                   ("smoothing", "Smoothing", 0.0, 0.9)]:
            r = ttk.Frame(mbox)
            r.pack(fill="x")
            ttk.Label(r, text=label, width=20).pack(side="left", padx=4)
            var = tk.DoubleVar(value=float(self.cfg["mouse"][key]))
            val = ttk.Label(r, text=f"{var.get():.2f}", width=5)
            s = ttk.Scale(r, from_=lo, to=hi, variable=var,
                          command=lambda _v, k=key, v=var, l=val: self._slide(k, v, l))
            s.pack(side="left", fill="x", expand=True)
            val.pack(side="left")
            self.sliders[key] = var
            self._slider_lbls[key] = val
        self.inv_var = tk.BooleanVar(value=bool(self.cfg["mouse"].get("invert_y")))
        prow = ttk.Frame(mbox)
        prow.pack(fill="x", pady=2)
        ttk.Checkbutton(prow, text="Invert Y", variable=self.inv_var,
                        command=self._invert).pack(side="left", padx=4)
        ttk.Button(prow, text="Default", command=lambda: self._preset("default")).pack(side="right", padx=4)
        ttk.Button(prow, text="PC feel", command=lambda: self._preset("pc")).pack(side="right")

        kbox = ttk.LabelFrame(self.root, text="Key mapping")
        kbox.pack(fill="x", **pad)
        r0 = ttk.Frame(kbox)
        r0.pack(fill="x", pady=3)
        ttk.Label(r0, text="Style:").pack(side="left", padx=4)
        self.style_var = tk.StringVar(value=config.STYLE_NAMES.get(self.cfg.get("style", "rdr2")))
        cb = ttk.Combobox(r0, textvariable=self.style_var, state="readonly", width=14,
                          values=list(config.STYLE_NAMES.values()))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self._style_changed)
        r = ttk.Frame(kbox)
        r.pack(fill="x", pady=3)
        ttk.Button(r, text="Edit mapping (config.json)", command=self.edit_cfg).pack(side="left", padx=4)
        ttk.Button(r, text="Reload", command=self.reload_cfg).pack(side="left")
        tk.Label(self.root, justify="left", font=("Segoe UI", 9), fg="#555", text=(
            "GTA 6 Default layout (RDR2 style):\n"
            "LMB punch (shoot while holding RMB), RMB aim, Shift run,\n"
            "Space jump, E interact,\n"
            "F enter/exit vehicle,\n"
            "R reload/melee, Ctrl crouch, Q cover, Tab holster, C look back,\n"
            "M map, middle mouse = hold to throw, wheel = scope zoom,\n"
            "Arrows = D-pad (Up phone).  In a car: W gas, S brake,\n"
            "LMB shoot, Q/X indicators, H lights. Everything else stays the same\n"
            "in a car.  GTA5 style: Z = minimap.")).pack(**pad)

    def _slide(self, key, var, label):
        self.cfg["mouse"][key] = round(var.get(), 3)
        label.config(text=f"{var.get():.2f}")
        self._save_later()

    PRESETS = {
        # linear, little smoothing, small anti-deadzone. Pair with in-game:
        # Look/Aim Acceleration lowest, Aim Response Curve Linear,
        # right-stick Deadzone lowest, Look/Aim Sensitivity 12-14.
        "pc": {"curve": 1.0, "smoothing": 0.2, "anti_deadzone": 0.08},
        "default": {"sensitivity": 1.0, "curve": 0.85, "smoothing": 0.45, "anti_deadzone": 0.18},
    }

    def _preset(self, name):
        for key, val in self.PRESETS[name].items():
            self.cfg["mouse"][key] = val
            self.sliders[key].set(val)
            lbl = self._slider_lbls.get(key)
            if lbl:
                lbl.config(text=f"{val:.2f}")
        config.save(self.cfg)
        if name == "pc":
            messagebox.showinfo(APP, (
                "PC feel is on.\n\nFor best results, in GTA 6 go to Settings > Controller:\n"
                "- Look / Aim Acceleration: lowest\n"
                "- Aim Response Curve: Linear\n"
                "- Deadzone (Right Stick): lowest\n"
                "- Look / Aim Sensitivity: 12-14\n\n"
                "Then adjust Sensitivity here until it feels right.\n"
                "If the camera drifts by itself, raise Anti-deadzone a little."))

    def _style_changed(self, _evt=None):
        name = self.style_var.get()
        style = next(k for k, v in config.STYLE_NAMES.items() if v == name)
        foot, veh = config.style_layout(style)
        self.mapper.release_all()
        self.cfg["style"] = style
        self.cfg["on_foot"] = foot
        self.cfg["vehicle"] = veh
        config.save(self.cfg)

    def _invert(self):
        self.cfg["mouse"]["invert_y"] = self.inv_var.get()
        config.save(self.cfg)

    def _save_later(self):
        if getattr(self, "_save_job", None):
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(400, lambda: config.save(self.cfg))

    def _poll(self):
        try:
            while True:
                kind, val = self.ui_q.get_nowait()
                if kind == "status":
                    ok = val == "CONNECTED"
                    self.status_lbl.config(text=val, foreground="#080" if ok else "#a00")
                    if not self.link.connected and not self.link.reconnecting \
                            and self.hooks.capturing:
                        self._set_capture(False)
                elif kind == "capture":
                    self._paint_capture()
                    self._tray_state(self.hooks.capturing)
                    if self.hooks.capturing:
                        self.hide()
                elif kind == "call":
                    val()
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _paint_capture(self):
        if self.hooks.capturing:
            mode = "VEHICLE" if self.mapper.vehicle else "ON FOOT"
            if self.mapper.minigame:
                mode += " + MINIGAME"
            self.capture_lbl.config(text=f"CAPTURE ON - {mode}", bg="#0a7d2c")
        else:
            self.capture_lbl.config(text="CAPTURE OFF", bg="#444")

    # ---------- hotkeys (called from hook thread) ----------
    def toggle_capture(self):
        if not self.hooks.capturing and not (self.link.connected or self.link.reconnecting):
            beep(False)
            self.ui_q.put(("status", "Connect to the PS5 first"))
            return
        self._set_capture(not self.hooks.capturing)

    def _set_capture(self, on: bool):
        self.hooks.set_capture(on)
        beep(on)
        self.ui_q.put(("capture", None))

    def toggle_minigame(self, on: bool):
        if on != self.mapper.minigame:
            self.mapper.set_minigame(on)
            self.ui_q.put(("capture", None))

    def toggle_vehicle(self):
        self.mapper.set_vehicle(not self.mapper.vehicle)
        self.ui_q.put(("capture", None))

    # ---------- actions ----------
    def _bg(self, work, done=None, fail_title="Error"):
        def run():
            try:
                res = work()
                if done:
                    self.ui_q.put(("call", lambda: done(res)))
            except Exception as exc:  # pylint: disable=broad-except
                logging.exception("action")
                msg = str(exc)
                self.ui_q.put(("call", lambda: messagebox.showerror(fail_title, msg)))
        threading.Thread(target=run, daemon=True).start()

    def find(self):
        self.status_lbl.config(text="Searching...")

        def done(found):
            if not found:
                self.status_lbl.config(text="No console found - type the IP (PS5: Settings > Network > Connection Status)")
                return
            ps5 = [d for d in found if d.get("host-type") == "PS5"] or found
            self.host_var.set(ps5[0]["host-ip"])
            self._save_host()
            self.status_lbl.config(text=f"Found {ps5[0].get('host-name')} ({ps5[0]['host-ip']})")
            self._refresh_account()
        self._bg(rp.find_consoles, done)

    def _save_host(self):
        self.cfg["host"] = self.host_var.get().strip()
        config.save(self.cfg)

    def _refresh_account(self):
        user, host = self.cfg.get("user"), self.cfg.get("host")
        if not user:
            self.account_lbl.config(text="PSN account: not linked")
            return
        self.account_lbl.config(text=f"PSN account: {user} (checking...)")

        def done(ok):
            self.account_lbl.config(text=f"PSN account: {user}" + ("  ✓ linked" if ok else "  - not linked to this PS5"))
        if host:
            self._bg(lambda: rp.is_linked(host, user), done)

    def link_wizard(self):
        self._save_host()
        if not self.cfg["host"]:
            messagebox.showinfo(APP, "Find the PS5 first (or type its IP).")
            return
        messagebox.showinfo(APP, (
            "Step 1 of 2: a browser window will open.\n\n"
            "Sign in to your PlayStation account. You will end up on a page that "
            "looks empty or says 'redirect'.\n\nCopy the full address (URL) of that "
            "page and paste it in the next box."))
        webbrowser.open(rp.login_url())
        url = simpledialog.askstring(APP, "Paste the address of the 'redirect' page:", parent=self.root)
        if not url:
            return
        pin = simpledialog.askstring(APP, (
            "Step 2 of 2: on the PS5 go to\nSettings > System > Remote Play > Link Device\n\n"
            "Type the 8-digit number shown on the TV:"), parent=self.root)
        if not pin:
            return
        host = self.cfg["host"]

        def work():
            name = rp.add_psn_account(url)
            rp.link_console(host, name, pin)
            return name

        def done(name):
            self.cfg["user"] = name
            config.save(self.cfg)
            messagebox.showinfo(APP, f"Linked {name} to the PS5. Press Connect.")
            self._refresh_account()
        self._bg(work, done, "Linking failed")

    def connect(self):
        self._save_host()
        if not self.cfg["host"] or not self.cfg.get("user"):
            messagebox.showinfo(APP, "Find the PS5 and link your account first.")
            return
        if self.link.connected:
            return
        self.link.connect(self.cfg["host"], self.cfg["user"])

    def edit_cfg(self):
        config.save(self.cfg)
        try:
            os.startfile(config.config_path())  # pylint: disable=no-member
        except Exception:  # pylint: disable=broad-except
            messagebox.showinfo(APP, config.config_path())

    def reload_cfg(self):
        new = config.load()
        self.cfg.clear()
        self.cfg.update(new)
        for key, var in self.sliders.items():
            var.set(float(self.cfg["mouse"][key]))
        self.inv_var.set(bool(self.cfg["mouse"].get("invert_y")))
        messagebox.showinfo(APP, "Mapping reloaded.")

    def quit(self):
        if self.tray:
            self.tray.stop()
        self.hooks.set_capture(False)
        self.hooks.stop()
        self.link.disconnect()
        self.root.after(300, self.root.destroy)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
