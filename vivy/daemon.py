"""Daemon Kiki: menyatukan STT + TTS + Face + Intent/Brain."""
import os
import signal
import sys
import threading
import time

from . import brain, config as C, intents
from .face import Face
from .stt import STT
from .tts import TTS

CFG_PATH = os.environ.get("VIVY_CONFIG") or os.path.join(C.PKG_DIR, "config.yaml")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(C.F_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


class Kiki:
    def __init__(self):
        self.cfg = C.load(CFG_PATH if os.path.exists(CFG_PATH) else None)
        self.name = self.cfg["assistant"]["name"]
        os.environ["VIVY_ALLOW_POWER"] = "1" if self.cfg["security"].get("allow_power") else "0"
        os.environ["VIVY_VOL_STEP"] = str(self.cfg["media"].get("volume_step", 8))
        self.face = Face(self.cfg)
        self.tts = None
        self.stt = None
        self.pending_confirm = None
        self.busy = False
        self.muted = False

    # ---------- bootstrap ----------
    def start(self):
        C.write_file(C.PID, str(os.getpid()))
        self.face.start()
        time.sleep(0.6)
        self.face.set_mood("happy", 2.0)
        self.face.say(f"Hai, aku {self.name}. Aku siap membantu.")

        self.tts = TTS(
            self.cfg,
            on_start=self._speak_start,
            on_level=self._speak_level,
            on_end=self._speak_end,
            on_state=lambda k, v: log(f"tts {k}: {v}"),
        )
        self.tts.start()

        self.stt = STT(self.cfg, on_text=self._on_text, on_state=self._on_state)
        try:
            self.stt.start()
        except Exception as e:
            log(f"FATAL STT: {e}")
            self.face.set_mood("error", 5)
            self.face.say("Maaf, aku gagal memuat pengenalan suara.")
            return 1

        threading.Thread(target=self._control_watch, daemon=True).start()
        self._say_ready()
        return 0

    def _say_ready(self):
        time.sleep(1.2)
        if self.cfg["stt"].get("require_wake", True):
            self.face.say(f"Katakan '{self.name}' untuk mula.")
        else:
            self.face.say("Aku siap dengerin.")

    # ---------- STT callbacks ----------
    def _on_state(self, kind, value):
        if kind == "wake":
            self.face.set_mood("happy", 1.2)
        elif kind == "partial" and self.stt and self.stt.armed:
            self.face.set_mood("listening")
        elif kind == "level":
            self.face.set_mic(value)
        elif kind == "armed":
            self.face.set_mood("listening")
        elif kind == "ready":
            log(f"siap dengerin ({value})")
        elif kind == "loading":
            log(value)
        elif kind in ("error", "warn"):
            log(f"{kind}: {value}")

    def _on_text(self, text):
        text = text.strip()
        if not text:
            return
        log(f"heard: {text}")
        self.face.set_mood("thinking")
        threading.Thread(target=self._handle, args=(text,), daemon=True).start()

    # ----------kotak masuk: remote command file ----------
    def _control_watch(self):
        last = ""
        while True:
            cmd = C.read_file(C.F_CMD)
            if cmd and cmd != last:
                last = cmd
                try:
                    os.unlink(C.F_CMD)
                except OSError:
                    pass
                if cmd == "silence":
                    self.mute(True)
                elif cmd == "unsilence":
                    self.mute(False)
                elif cmd == "toggle":
                    self.mute(not self.muted)
                elif cmd == "hide":
                    self.hide()
                elif cmd == "show":
                    self.show()
                elif cmd == "quit":
                    self.shutdown()
                elif cmd == "sleep":
                    self.face.set_mood("sleep", 3600)
            say = C.read_file(C.F_SAY)
            if say:
                try:
                    os.unlink(C.F_SAY)
                except OSError:
                    pass
                self.face.say(say)
                self.tts.say(say)
            wake = C.read_file(C.F_WAKE)
            if wake:
                try:
                    os.unlink(C.F_WAKE)
                except OSError:
                    pass
                self.stt.force_arm()
            fired = C.read_file(C.RUNTIME / "timer_done")
            if fired:
                try:
                    os.unlink(C.RUNTIME / "timer_done")
                except OSError:
                    pass
                self.face.say(fired)
                self.tts.say(fired)
                self.face.set_mood("happy", 3.0)
            time.sleep(0.25)

    def mute(self, m=True):
        self.muted = m
        if self.stt:
            self.stt.mute(m)
        if m:
            self.tts.stop()
            self.face.set_mood("sleep", 3600)
            self.face.subtitle = ""
        else:
            self.tts.running = True
            self.face.set_mood("happy", 1.5)

    def hide(self):
        self.face.running = False
        log("wajah disembunyikan (vivy show)")

    def show(self):
        self.face = Face(self.cfg)
        self.face.start()
        log("wajah ditampilkan")

    # ---------- TTS callbacks ----------
    def _speak_start(self, text):
        self.busy = True
        self.face.say(text)
        self.face.set_mood("speaking")
        if self.stt:
            self.stt.mute(True)

    def _speak_level(self, level, dur):
        self.face.set_mouth(level)

    def _speak_end(self, text):
        self.busy = False
        self.face.set_mouth(0.0)
        if self.stt and not self.muted:
            self.stt.mute(False)
        self.face.set_mood("idle", 1.0)

    # ---------- Pemrosesan ----------
    def _handle(self, text):
        try:
            if self.pending_confirm:
                reply, mood, name = intents.confirm(text, self.cfg, self.pending_confirm)
                if name == "need_yes_no":
                    self._speak(reply, mood, name)
                    return
                self.pending_confirm = None
                self._speak(reply, mood, name)
                return

            reply, mood, name = intents.handle(text, self.cfg, self)
            if name and name.startswith("confirm:"):
                self.pending_confirm = name
                self._speak(reply, mood or "thinking")
                return
            if reply is None:
                # mungkin percakapan biasa
                mood2 = brain.detect_mood(intents.norm(text))
                reply = brain.reply(text, self.cfg, mood2)
                mood = brain.mood_for(mood2, text)
                name = "chat"
            self._speak(reply, mood or "idle", name)
        except Exception as e:
            log(f"error handling '{text}': {e!r}")
            self._speak("Maaf, ada yang error.", "error")

    def _speak(self, text, mood=None, intent=None):
        if not text:
            return
        if mood and mood not in ("speaking",):
            self.face.set_mood(mood)
        if mood in ("happy", "excited", "love", "sad", "error"):
            self.face.set_mood(mood, 2.5)
        self.tts.say(text)
        if intent:
            log(f"intent={intent} -> {text}")

    # ---------- shutdown ----------
    def shutdown(self):
        log(" shutting down")
        self.face.running = False
        if self.stt:
            self.stt.stop()
        if self.tts:
            self.tts.stop()
        try:
            os.unlink(C.PID)
        except OSError:
            pass
        time.sleep(0.3)
        sys.exit(0)


def main():
    k = Kiki()
    def _sig(signum, frame):
        k.shutdown()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    rc = k.start()
    if rc:
        return rc
    while k.face.running or True:
        time.sleep(1)
    return 0