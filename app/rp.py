"""Remote Play connection that only sends controller input (video is ignored)."""
import asyncio
import logging
import threading
import time
import warnings

warnings.filterwarnings("ignore", message="av not installed")

from pyremoteplay.device import RPDevice          # noqa: E402
from pyremoteplay.ddp import search               # noqa: E402
from pyremoteplay.oauth import get_login_url, get_user_account  # noqa: E402
from pyremoteplay.profile import format_user_account  # noqa: E402

_LOGGER = logging.getLogger("bengo.rp")
TICK = 0.004  # 250 Hz


def find_consoles() -> list:
    return [d for d in search() if d.get("host-ip")]


def login_url() -> str:
    return get_login_url()


def add_psn_account(redirect_url: str) -> str:
    """Return PSN name after saving the account. Raises on failure."""
    data = get_user_account(redirect_url.strip())
    if not data:
        raise RuntimeError("Could not read the PSN account from that link.")
    profile = format_user_account(data)
    if profile is None:
        raise RuntimeError("Could not create a profile for that account.")
    profiles = RPDevice.get_profiles()
    profiles.update_user(profile)
    profiles.save()
    return profile.name


def link_console(host: str, user: str, pin: str):
    dev = RPDevice(host)
    if not dev.get_status():
        raise RuntimeError("PS5 not found at that address. Is it on?")
    if not dev.register(user, pin.replace(" ", ""), timeout=5.0):
        raise RuntimeError("Linking failed. Check the PIN (it changes every few minutes).")


def is_linked(host: str, user: str) -> bool:
    try:
        dev = RPDevice(host)
        if not dev.get_status():
            return False
        return user in dev.get_users()
    except Exception:  # pylint: disable=broad-except
        return False


def _clamp(point):
    return tuple(max(-1.0, min(1.0, float(v))) for v in point)


class Link:
    """Owns the Remote Play session and the thread that sends input."""

    def __init__(self, mapper, on_status):
        self.mapper = mapper
        self.on_status = on_status
        self.device = None
        self.loop = None
        self.connected = False
        self._stop = threading.Event()

    def connect(self, host: str, user: str):
        self._stop.clear()
        threading.Thread(target=self._run, args=(host, user), daemon=True).start()

    def disconnect(self):
        self._stop.set()

    # ---------- session thread ----------
    def _run(self, host, user):
        try:
            self.device = RPDevice(host)
            self.on_status("Looking for PS5...")
            if not self.device.get_status():
                raise RuntimeError("PS5 not reachable.")
            if not self.device.is_on:
                self.on_status("Waking PS5 from rest mode...")
                self.device.wakeup(user)
                if not self.device.wait_for_wakeup(timeout=60):
                    raise RuntimeError("PS5 did not wake up.")
                time.sleep(5)
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            # Lowest video settings: we never show this video, Veyra does.
            session = self.device.create_session(
                user, loop=self.loop, resolution="360p", fps="low", quality="very_low")
            if session is None:
                raise RuntimeError("Account not linked to this PS5.")
            self.on_status("Connecting to Remote Play...")
            ok = self.loop.run_until_complete(self.device.connect())
            if not ok:
                raise RuntimeError(f"Remote Play failed: {self.device.session.error}")
            ready = self.loop.run_until_complete(self.device.async_wait_for_session())
            if not ready:
                raise RuntimeError("Remote Play timed out.")
            self.connected = True
            self.on_status("CONNECTED")
            threading.Thread(target=self._sender, daemon=True).start()
            self.loop.run_until_complete(self._wait_end())
            err = self.device.session.error
            self.connected = False
            self.device.disconnect()
            self.loop.run_until_complete(asyncio.sleep(0.5))
            self.on_status(f"Disconnected{': ' + err if err else ''}")
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("session")
            self.connected = False
            self.on_status(f"Error: {exc}")

    async def _wait_end(self):
        while not self._stop.is_set() and not self.device.session.is_stopped:
            await asyncio.sleep(0.2)

    # ---------- input sender thread ----------
    def _sender(self):
        ctrl = self.device.controller
        last = time.perf_counter()
        while self.connected and not self._stop.is_set():
            time.sleep(TICK)
            now = time.perf_counter()
            dt, last = now - last, now
            try:
                for button, pressed in self.mapper.take_events():
                    ctrl.button(button, "press" if pressed else "release")
                ctrl.stick("left", point=_clamp(self.mapper.left_stick()))
                ctrl.stick("right", point=_clamp(self.mapper.right_stick(dt)))
                ctrl.update_sticks()
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("sender")
        try:
            for button in list(self.mapper._refs):  # pylint: disable=protected-access
                ctrl.button(button, "release")
        except Exception:  # pylint: disable=broad-except
            pass
