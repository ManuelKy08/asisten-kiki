"""Konfigurasi loader + path."""
import os
import shutil
from pathlib import Path

import yaml

PKG_DIR = Path(__file__).resolve().parent.parent
RUNTIME = Path(os.environ.get("VIVY_RUNTIME", Path.home() / ".local/share/vivy"))
RUNTIME.mkdir(parents=True, exist_ok=True)

# channel komunikasi CLI <-> daemon
F_WAKE = RUNTIME / "wake"
F_SAY = RUNTIME / "say"
F_CMD = RUNTIME / "cmd"
F_LOG = RUNTIME / "vivy.log"
PID = RUNTIME / "vivy.pid"

DEFAULTS = {
    "assistant": {"name": "Vivy", "lang": "id"},
    "face": {
        "width": 420, "height": 560, "scale": 2, "pos": "bottom-right",
        "custom_pos": [60, 60], "margin": 36, "subtitle": True,
        "transparent": True, "always_on_top": True, "hide_taskbar": True,
        "fps": 30, "body": "#6ee7ff", "body_dark": "#3aa7d8", "accent": "#ffd166",
    },
    "stt": {
        "model": "", "device": "", "sample_rate": 16000,
        "wake_words": ["halo", "hai vivy", "hey vivy", "vivy", "oke halo", "assisten"],
        "require_wake": True, "wake_min_confidence": 0.3, "silence_ms": 1100,
        "max_utterance_s": 15, "min_words": 1, "mic_rms_gate": 0.006,
    },
    "tts": {
        "engine": "auto", "piper_bin": "piper", "piper_model": "",
        "piper_bin_dir": "", "espeak_bin": "espeak-ng", "espeak_voice": "id",
        "rate": 1.0, "pitch": 50,
    },
    "brain": {
        "ai_enabled": False, "ai_endpoint": "http://localhost:11434",
        "ai_model": "llama3.1:8b", "ai_api_key": "", "history": 8,
        "system": (
            "Kamu Vivy, asisten suara desktop yang hangat dan care. "
            "Jawab singkat dan hangat dalam Bahasa Indonesia."
        ),
    },
    "shell": {
        "terminal": "auto", "browser": "auto", "file_manager": "auto",
        "screenshot_cmd": "auto", "clipboard_read": "auto", "clipboard_write": "auto",
    },
    "media": {"volume_step": 8},
    "apps": {}, "sites": {}, "security": {"confirm_power": True, "allow_power": True},
}


def deep_merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _normalize(cfg):
    """Buang key dengan spasi/tyo dan lowercase semua key dict."""
    out = {}
    for k, v in cfg.items():
        if not isinstance(v, dict):
            out[str(k).strip().lower()] = v
            continue
        nk = str(k).strip().lower()
        nk = nk.replace("terminal emulator", "terminal")
        nk = " ".join(nk.split())
        out[nk] = v
    return out


def load(path=None):
    cfg = yaml.safe_load(open(path)) if path else {}
    return deep_merge(DEFAULTS, _normalize(cfg or {}))


def run_quiet(cmd, **kw):
    """Jalankan perintah tanpa nozzle stdout/stderr."""
    import subprocess
    try:
        return subprocess.run(cmd, capture_output=True, timeout=kw.pop("timeout", 20), **kw)
    except Exception as e:
        class R:
            returncode = 127
            stdout = b""
            stderr = str(e).encode()
        return R()


def capture(cmd, timeout=10):
    import subprocess
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.stdout.decode(errors="replace")
    except Exception:
        return ""


def write_file(path, text):
    try:
        Path(path).write_text(str(text))
    except Exception:
        pass


def read_file(path, default=""):
    try:
        return Path(path).read_text().strip()
    except Exception:
        return default


def which(binname, candidates=()):
    """Cari binary; 'auto' -> coba daftar kandidat."""
    if not binname:
        return None
    if binname != "auto":
        return shutil.which(binname) or (binname if os.path.isfile(binname) else None)
    for c in candidates:
        p = shutil.which(c)
        if p:
            return p
    return None