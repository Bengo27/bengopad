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
from pyremoteplay.stream_packets import FeedbackHeader  # noqa: E402

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
    """Owns the Remote Play session and the thread that sends input.

    Every packet is sent from the asyncio loop thread: the packet cipher keeps a
    counter, and sending from two threads at once corrupts it, which makes the
    PS5 drop the session after a few seconds.
    """

    MAX_RETRIES = 5

    def __init__(self, mapper, on_status):
        self.mapper = mapper
        self.on_status = on_status
        self.device = None
        self.loop = None
        self.connected = False
        self.reconnecting = False
        self._stop = threading.Event()
        self._last_state_sent = 0.0
        self._ok_since = 0

    def connect(self, host: str, user: str):
        self._stop.clear()
        threading.Thread(target=self._run, args=(host, user), daemon=True).start()

    def disconnect(self):
        self._stop.set()

    # ---------- session thread ----------
    def _run(self, host, user):
        retries = 0
        while not self._stop.is_set():
            err = self._session_once(host, user)
            self.connected = False
            if self._stop.is_set():
                self.reconnecting = False
                self.on_status("Disconnected")
                return
            _LOGGER.warning("session ended: %s", err)
            retries += 1
            if retries > self.MAX_RETRIES:
                self.reconnecting = False
                self.on_status(f"Disconnected: {err}")
                return
            self.reconnecting = True
            self.on_status(f"Reconnecting ({retries}/{self.MAX_RETRIES})... [{err}]")
            time.sleep(2)
            if self._ok_since and time.time() - self._ok_since > 60:
                retries = 0  # it had been stable, start counting again

    def _session_once(self, host, user) -> str:
        self._ok_since = 0
        try:
            self.device = RPDevice(host)
            self.on_status("Looking for PS5...")
            if not self.device.get_status():
                return "PS5 not reachable"
            if not self.device.is_on:
                self.on_status("Waking PS5 from rest mode...")
                self.device.wakeup(user)
                if not self.device.wait_for_wakeup(timeout=60):
                    return "PS5 did not wake up"
                time.sleep(5)
            if self.loop and not self.loop.is_closed():
                self.loop.close()
            self.loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(self.loop)
            # Lowest video settings: we never show this video, Veyra does.
            session = self.device.create_session(
                user, loop=self.loop, resolution="360p", fps="low", quality="very_low")
            if session is None:
                return "Account not linked to this PS5"
            self.on_status("Connecting to Remote Play...")
            if not self.loop.run_until_complete(self.device.connect()):
                return f"Remote Play failed: {self.device.session.error}"
            if not self.loop.run_until_complete(self.device.async_wait_for_session()):
                return "Remote Play timed out"
            self.connected = True
            self.reconnecting = False
            self._ok_since = time.time()
            self.on_status("CONNECTED")
            threading.Thread(target=self._sender, daemon=True).start()
            self.loop.run_until_complete(self._wait_end())
            sess = self.device.session
            err = sess.error or sess.disconnect_reason or "session closed"
            self.connected = False
            try:
                self.device.disconnect()
                self.loop.run_until_complete(asyncio.sleep(0.5))
            except Exception:  # pylint: disable=broad-except
                pass
            return err
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("session")
            return str(exc)

    async def _wait_end(self):
        while not self._stop.is_set() and not self.device.session.is_stopped:
            await asyncio.sleep(0.2)

    # ---------- input ----------
    def _apply(self, events, left, right):
        """Runs on the loop thread."""
        if not self.connected:
            return
        ctrl = self.device.controller
        try:
            for button, pressed in events:
                ctrl.button(button, "press" if pressed else "release")
            ctrl.stick("left", point=left)
            ctrl.stick("right", point=right)
            before = ctrl._sequence_state  # pylint: disable=protected-access
            ctrl.update_sticks()
            now = time.perf_counter()
            if ctrl._sequence_state != before:  # pylint: disable=protected-access
                self._last_state_sent = now
            elif now - self._last_state_sent > 0.2:
                # keep-alive: resend the current state at least every 200 ms
                ctrl.session.stream.send_feedback(
                    FeedbackHeader.Type.STATE, ctrl._sequence_state,  # pylint: disable=protected-access
                    state=ctrl.stick_state)
                ctrl._sequence_state += 1  # pylint: disable=protected-access
                self._last_state_sent = now
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("apply")

    def _sender(self):
        loop = self.loop
        last = time.perf_counter()
        while self.connected and not self._stop.is_set():
            time.sleep(TICK)
            now = time.perf_counter()
            dt, last = now - last, now
            events = self.mapper.take_events()
            left = _clamp(self.mapper.left_stick())
            right = _clamp(self.mapper.right_stick(dt))
            try:
                loop.call_soon_threadsafe(self._apply, events, left, right)
            except RuntimeError:
                break
