"""CLI: vivy <command>."""
import argparse
import os
import signal
import time

from . import config as C

CFG_PATH = os.environ.get("VIVY_CONFIG") or os.path.join(C.PKG_DIR, "config.yaml")


def _alive():
    pid = C.read_file(C.PID)
    if not pid:
        return None
    try:
        os.kill(int(pid), 0)
        return int(pid)
    except Exception:
        return None


def cmd_start(args):
    pid = _alive()
    if pid and not args.force:
        print(f"kiki sudah jalan (pid {pid}).")
        return 0
    if args.force and pid:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.6)
    os.environ.setdefault("VIVY_CONFIG", CFG_PATH)
    from .daemon import Kiki
    k = Kiki()
    k.start()
    while True:
        time.sleep(1)


def cmd_stop(args):
    pid = _alive()
    if not pid:
        print("kiki tidak sedang jalan.")
        return 0
    os.kill(pid, signal.SIGTERM)
    print(f"kiki dihentikan (pid {pid}).")
    return 0


def cmd_status(args):
    pid = _alive()
    if pid:
        print(f"kiki jalan (pid {pid})")
    else:
        print("kiki tidak jalan")
    return 0


def cmd_say(args):
    if not _alive():
        print("kiki tidak jalan; start dulu.")
        return 1
    C.write_file(C.F_SAY, " ".join(args.text))
    return 0


def cmd_wake(args):
    if not _alive():
        print("kiki tidak jalan; start dulu.")
        return 1
    C.write_file(C.F_WAKE, "1")
    return 0


def _cmd_write(text):
    if not _alive():
        print("kiki tidak jalan; start dulu.")
        return 1
    C.write_file(C.F_CMD, text)
    return 0


def cmd_mute(args):
    return _cmd_write("silence")


def cmd_unmute(args):
    return _cmd_write("unsilence")


def cmd_toggle(args):
    return _cmd_write("toggle")


def cmd_hide(args):
    return _cmd_write("hide")


def cmd_show(args):
    return _cmd_write("show")


def cmd_sleep(args):
    return _cmd_write("sleep")


def cmd_quit(args):
    pid = _alive()
    if not pid:
        print("kiki tidak jalan.")
        return 0
    C.write_file(C.F_CMD, "quit")
    return 0


def cmd_test(args):
    """Uji intent tanpa mic/TTS."""
    from . import brain, intents
    cfg = C.load(CFG_PATH if os.path.exists(CFG_PATH) else None)
    tests = args.text or [
        "buka youtube", "cari di youtube lagu djakarta", "cari wedangereum",
        "buka browser", "volume naik", "volume turun", "diamkan suara",
        "screenshot", "jam berapa", "wifi nyala", "kecerahan naik",
        "buka firefox", "tutup jendela", "timer 10 menit",
        "aku sedih banget hari ini", "aku cinta kamu", "senang banget hari ini",
        "aku capek kerjaan banget", "nama kamu siapa", "makasih ya",
        "hello", "bantuan", "shutdown",
    ]
    for t in tests:
        r, mood, name = intents.handle(t, cfg)
        if r is None:
            m = brain.detect_mood(intents.norm(t))
            r, mood, name = brain.reply(t, cfg, m), brain.mood_for(m, t), "chat"
        print(f"{t!r:42} -> [{name}/{mood}] {r}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="vivy", description="Kiki - asisten suara + wajah animasi")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("start", help="jalanankan kiki di foreground")
    s.add_argument("-f", "--force", action="store_true")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("stop"); s.set_defaults(func=cmd_stop)
    s = sub.add_parser("status"); s.set_defaults(func=cmd_status)
    s = sub.add_parser("quit", aliases=["exit"]); s.set_defaults(func=cmd_quit)
    s = sub.add_parser("mute", aliases=["bisu"]); s.set_defaults(func=cmd_mute)
    s = sub.add_parser("unmute", aliases=["bicara"]); s.set_defaults(func=cmd_unmute)
    s = sub.add_parser("toggle"); s.set_defaults(func=cmd_toggle)
    s = sub.add_parser("hide"); s.set_defaults(func=cmd_hide)
    s = sub.add_parser("show"); s.set_defaults(func=cmd_show)
    s = sub.add_parser("sleep", aliases=["tidur"]); s.set_defaults(func=cmd_sleep)
    s = sub.add_parser("wake", help="aktifkan mikrofon langsung")
    s.set_defaults(func=cmd_wake)

    s = sub.add_parser("say"); s.add_argument("text", nargs="+"); s.set_defaults(func=cmd_say)
    s = sub.add_parser("test", help="uji perintah di terminal")
    s.add_argument("text", nargs="*")
    s.set_defaults(func=cmd_test)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 0
    return args.func(args) or 0