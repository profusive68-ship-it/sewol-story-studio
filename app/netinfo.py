"""폰 접속 — LAN/Tailscale 주소, QR, 접속 비밀번호, 잠자기 방지."""
from __future__ import annotations

import shutil
import socket
import subprocess
from pathlib import Path

from .paths import BASE

QR_PATH = BASE / "config" / "remote_qr.png"
CAFFEINE_PID = BASE / "config" / "caffeinate.pid"
_caf: subprocess.Popen | None = None


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def tailscale_ip() -> str | None:
    exe = shutil.which("tailscale") or "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    if not (exe and Path(exe).exists()):
        return None
    try:
        r = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5)
        ip = (r.stdout or "").strip().splitlines()
        return ip[0].strip() if ip else None
    except Exception:
        return None


def qr_png(text: str) -> Path | None:
    try:
        import qrcode
        QR_PATH.parent.mkdir(parents=True, exist_ok=True)
        img = qrcode.make(text)
        img.save(QR_PATH)
        return QR_PATH
    except Exception:
        return None


def caffeinate(on: bool) -> dict:
    global _caf
    if on:
        if _caf and _caf.poll() is None:
            return {"on": True, "message": "이미 켜져 있습니다."}
        try:
            _caf = subprocess.Popen(["caffeinate", "-dimsu"])
            CAFFEINE_PID.parent.mkdir(parents=True, exist_ok=True)
            CAFFEINE_PID.write_text(str(_caf.pid), encoding="utf-8")
            return {"on": True, "message": "맥북이 잠들지 않습니다. (화면만 꺼짐)"}
        except Exception as e:
            return {"on": False, "message": f"켜지 못했습니다: {e}"}
    else:
        if _caf and _caf.poll() is None:
            _caf.terminate()
        try:
            if CAFFEINE_PID.exists():
                import os
                os.kill(int(CAFFEINE_PID.read_text().strip()), 15)
        except Exception:
            pass
        try:
            CAFFEINE_PID.unlink(missing_ok=True)
        except Exception:
            pass
        return {"on": False, "message": "잠자기 방지를 껐습니다."}


def caffeinate_on() -> bool:
    return bool(_caf and _caf.poll() is None)
