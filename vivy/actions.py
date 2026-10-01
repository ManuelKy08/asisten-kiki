"""Aksi nyata: buka app/URL, media, wifi, brightness, clipboard, power, dsb."""
import os
import re
import shutil
import subprocess
import threading
import time
import webbrowser

from . import config as C

BROWSERS = ["firefox", "chromium", "chromium-browser", "google-chrome-stable", "brave", "vivaldi"]
TERMINALS = ["alacritty", "kitty", "foot", "wezterm", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"]
FILE_MGR = ["thunar", "nemo", "nautilus", "pcmanfm", "dolphin"]


def _first(cands):
    for c in cands:
        p = shutil.which(c)
        if p:
            return p
    return None


def open_url(url):
    url = url if re.match(r"^https?://", url) else "https://" + url
    br = _first(BROWSERS)
    if br:
        C.run_quiet([br, "--new-window", url])
        return f"membuka {url}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return f"membuka {url}"


def open_app(name):
    name = (name or "").strip().lower()
    # 1) alias dari config
    mapping = _load_app_map()
    if name in mapping:
        target = mapping[name]
        if target == "auto":
            pass
        else:
            return _launch(target, name)
    # 2) alias bawaan
    aliases = {
        "browser": BROWSERS, "peramban": BROWSERS, "web": BROWSERS,
        "terminal": TERMINALS, "term": TERMINALS, "konsol": TERMINALS,
        "berkas": FILE_MGR, "file": FILE_MGR, "files": FILE_MGR,
        "explorer": FILE_MGR, "manajer file": FILE_MGR,
    }
    if name in aliases:
        binp = _first(aliases[name])
        return f"membuka {name}" if binp and not _launch(binp, name) else f"{name} tidak terpasang"
    # 3) .desktop
    if _desktop(name):
        return f"membuka {name}"
    # 4) binary langsung
    return _launch(name, name)


def _load_app_map():
    from . import config as _c
    try:
        cfg = _c.load(os.environ.get("VIVY_CONFIG"))
        return {str(k).lower(): v for k, v in (cfg.get("apps") or {}).items()}
    except Exception:
        return {}


def _desktop(name):
    dirs = [os.path.expanduser("~/.local/share/applications"),
            "/usr/local/share/applications", "/usr/share/applications"]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".desktop"):
                continue
            try:
                txt = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            nm = ""
            for line in txt.splitlines():
                if line.startswith("Name="):
                    nm = line[5:].strip().lower()
                    break
            base = f[:-8].replace("_", "-").lower()
            if name in (nm, base) or nm.startswith(name):
                C.run_quiet(["gtk-launch", f[:-8]])
                return True
    return False


def _launch(target, label):
    if target == "auto":
        target = _first(BROWSERS + TERMINALS)
        if not target:
            return f"{label} tidak ditemukan"
    r = subprocess.run(["sh", "-c", f"nohup {target} >/dev/null 2>&1 &"])
    if r.returncode == 0:
        return f"membuka {label}"
    return f"gagal membuka {label}"


# ---------- media ----------
def _pactl(*args):
    return C.run_quiet(["pactl", *args])


def volume(delta=None, mute=None, pct=None):
    step = int(os.environ.get("VIVY_VOL_STEP", "8"))
    if mute is not None:
        _pactl("set-sink-mute", "@DEFAULT_SINK@", "on" if mute else "off")
        return "suara dimatikan" if mute else "suara nyala"
    if delta is None and pct is None:
        out = C.capture(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        m = re.search(r"(\d+)%", out)
        return f"volume {m.group(1)} persen" if m else "volume tidak terbaca"
    if pct is not None:
        pct = max(0, min(100, int(pct)))
        _pactl("set-sink-volume", "@DEFAULT_SINK@", f"{pct}%")
    else:
        rel = f"{step:+d}%"
        r = _pactl("set-sink-volume", "@DEFAULT_SINK@", rel)
        if r.returncode != 0:
            _pactl("set-sink-volume", "@DEFAULT_SINK@", f"{step}%{'+' if delta > 0 else '-'}")
    out = C.capture(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    m = re.search(r"(\d+)%", out)
    return f"volume {m.group(1)} persen" if m else "volume diubah"


def media(action):
    if not C.which("playerctl"):
        return "playerctl belum terpasang"
    C.run_quiet(["playerctl", action])
    names = {"play-pause": ("main lagi", "jeda"), "next": "lagu berikutnya",
             "previous": "lagu sebelumnya", "play": "main", "pause": "jeda"}
    return f"{names.get(action, action)}"


def brightness(delta=None):
    if delta is None:
        if C.which("brightnessctl"):
            out = C.capture(["brightnessctl", "get"])
            m = re.search(r"[\d.]+", out)
            return f"kecerahan {m.group(0)} persen" if m else "kecerahan tidak terbaca"
        out = C.capture(["xbacklight", "-get"])
        m = re.search(r"[\d.]+", out)
        return f"kecerahan {m.group(0)} persen" if m else "kecerahan tidak terbaca"
    step = 10
    if C.which("brightnessctl"):
        C.run_quiet(["brightnessctl", "set", f"{delta:+d}%"])
    else:
        C.run_quiet(["xbacklight", "-inc" if delta > 0 else "-dec", str(step)])
    return "kecerahan dinaikkan" if delta > 0 else "kecerahan diturunkan"


# ---------- sistem ----------
def wifi(state=None):
    if not C.which("nmcli"):
        return "nmcli tidak ada"
    if state is None:
        out = C.capture(["nmcli", "-t", "radio", "wifi"])
        on = "enabled" in out
        return f"wifi {'nyala' if on else 'mati'}"
    C.run_quiet(["nmcli", "radio", "wifi", "on" if state else "off"])
    return f"wifi {'dinyalakan' if state else 'dimatikan'}"


def bluetooth(state=None):
    if not C.which("bluetoothctl"):
        return "bluetoothctl tidak ada"
    if state is None:
        return "bluetooth siap"
    C.run_quiet(["bluetoothctl", "power", "on" if state else "off"])
    return f"bluetooth {'dinyalakan' if state else 'dimatikan'}"


def screenshot():
    for tool, args in (("scrot", ["-f"]), ("maim", ["-s", "~/Pictures/screenshot-$(date +%F-%H%M%S).png"]),
                       ("grim", [os.path.expanduser("~/Pictures/screenshot.png")])):
        if C.which(tool):
            os.makedirs(os.path.expanduser("~/Pictures"), exist_ok=True)
            C.run_quiet([tool, *args])
            return "screenshot diambil"
    return "tidak ada alat screenshot"


def copy(text):
    cmd = _clip_cmd("write")
    if not cmd:
        return "clipboard tidak tersedia"
    C.run_quiet(["sh", "-c", f"{cmd} <<'VIVYEOF'\n{text}\nVIVYEOF"])
    return "disalin ke clipboard"


def paste():
    cmd = _clip_cmd("read")
    if not cmd:
        return "clipboard tidak tersedia"
    return C.capture(["sh", "-c", cmd]).strip()


def _clip_cmd(mode):
    if C.which("xclip"):
        return "xclip -selection clipboard -i" if mode == "write" else "xclip -selection clipboard -o"
    if C.which("xsel"):
        return "xsel -b -i" if mode == "write" else "xsel -b -o"
    if C.which("wl-copy") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wl-copy" if mode == "write" else "wl-paste --no-newline"
    return None


def window(action):
    if not C.which("wmctrl"):
        return "wmctrl tidak ada"
    if action == "close":
        C.run_quiet(["wmctrl", "-c", ":ACTIVE:"])
        return "jendela ditutup"
    if action == "maximize":
        C.run_quiet(["wmctrl", "-r", ":ACTIVE:", "-b", "add,maximized_vert,maximized_horz"])
        return "jendela dimaksimumkan"
    if action == "minimize":
        C.run_quiet(["xdotool", "key", "super+h"])
        return "jendela disembunyikan"
    return "ok"


def openbox(action):
    if action == "desktop":
        C.run_quiet(["xdotool", "key", "super+d"])
        return "tampilkan desktop"
    if action == "lock":
        C.run_quiet(["xsetlock", "screensaver"])
        return "layar dikunci"
    return "ok"


def power(action):
    if not os.environ.get("VIVY_ALLOW_POWER", "1") == "1":
        return "perintah daya dimatikan di config"
    cmd = {"shutdown": "systemctl poweroff", "reboot": "systemctl reboot",
           "suspend": "systemctl suspend"}.get(action)
    if not cmd:
        return "tidak dikenal"
    C.run_quiet(["sh", "-c", f"({cmd}) &"])
    time.sleep(1.5)
    return f"{action} dijalankan"


def time_info():
    now = time.localtime()
    return time.strftime("pukul %H.%M", now), now


def notes(action, text=""):
    path = os.path.expanduser("~/.local/share/kiki/notes.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if action == "add":
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"- {text}\n")
        return "catatan disimpan"
    if action == "read":
        try:
            lines = [l.strip("- ").strip() for l in open(path, encoding="utf-8") if l.strip()]
        except FileNotFoundError:
            return "belum ada catatan"
        return "catatanmu: " + "; ".join(lines[-8:]) if lines else "belum ada catatan"
    return "ok"


def timer(seconds, label=""):
    from . import config as _c

    def _go():
        msg = f"Waktu habis! {label}".strip()
        if _c.which("notify-send"):
            subprocess.Popen(["notify-send", "Kiki", msg])
        C.run_quiet(["sh", "-c", "printf '\\a' > /dev/tty 2>/dev/null || true"])
        try:
            _c.write_file(_c.RUNTIME / "timer_done", msg)
        except Exception:
            pass

    t = threading.Timer(seconds, _go)
    t.daemon = True
    t.start()
    mins, secs = int(seconds // 60), int(seconds % 60)
    return f"timer {mins} menit {secs} detik" if mins else f"timer {secs} detik"