"""Self-update from the latest GitHub release of Bengo27/bengopad."""
import os
import subprocess
import sys
import tempfile

import requests

REPO = "Bengo27/bengopad"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET = "BengoPad.exe"


def _ver(text: str) -> tuple:
    parts = []
    for p in text.lstrip("vV").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check(current: str):
    """Return (version, download_url) if a newer release exists, else None."""
    resp = requests.get(API, timeout=8, headers={"Accept": "application/vnd.github+json"})
    if resp.status_code != 200:
        return None
    data = resp.json()
    tag = data.get("tag_name", "")
    if _ver(tag) <= _ver(current):
        return None
    for asset in data.get("assets", []):
        if asset.get("name") == ASSET:
            return tag.lstrip("vV"), asset["browser_download_url"]
    return None


def can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def download_and_restart(url: str, progress=None):
    """Download the new exe, then swap it in with a tiny batch file and restart."""
    exe = sys.executable
    new = exe + ".new"
    with requests.get(url, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0)) or None
        done = 0
        with open(new, "wb") as f:
            for chunk in resp.iter_content(256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    bat = os.path.join(tempfile.gettempdir(), "bengopad_update.bat")
    with open(bat, "w", encoding="utf-8") as f:
        f.write(
            "@echo off\r\n"
            "set n=0\r\n"
            "ping -n 3 127.0.0.1 >nul\r\n"
            ":retry\r\n"
            f'move /y "{new}" "{exe}" >nul 2>&1 && goto ok\r\n'
            "set /a n+=1\r\n"
            "if %n% geq 20 goto ok\r\n"
            "ping -n 2 127.0.0.1 >nul\r\n"
            "goto retry\r\n"
            ":ok\r\n"
            f'start "" "{exe}"\r\n'
            'del "%~f0"\r\n'
        )
    subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)  # CREATE_NO_WINDOW
