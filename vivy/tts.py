"""TTS: Piper (offline, natural) -> espeak-ng fallback -> bisu.

Lip-sync:.wav disintesis ke memory, level RMS dikirim per frame ke UI wajah.
"""
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import wave

import numpy as np

from . import config as C


def _synth_to_wav(text, cfg, path):
    engine = cfg.get("engine", "auto")
    t = cfg["tts"]

    piper = C.which(t.get("piper_bin", "piper")) if (t.get("piper_bin_dir") or t.get("piper_model")) else \
        C.which(t.get("piper_bin", "piper"))
    model = t.get("piper_model") or ""

    if engine in ("auto", "piper") and piper and model and os.path.exists(model):
        cmd = [piper, "--model", model, "--output_file", path,
               "--length_scale", str(1.0 / max(float(t.get("rate", 1.0)), 0.1))]
        try:
            r = subprocess.run(cmd, input=text.encode(), capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.getsize(path) > 100:
                return path
        except Exception:
            pass

    esp = C.which(t.get("espeak_bin", "espeak-ng"))
    if engine in ("auto", "piper", "espeak") and esp:
        cmd = [esp, "-v", str(t.get("espeak_voice", "id")), "-s", "165",
               "-p", str(t.get("pitch", 50)), "-w", path]
        try:
            r = subprocess.run(cmd + [text], capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.getsize(path) > 100:
                return path
        except Exception:
            pass

    return None


class TTS:
    def __init__(self, cfg, on_start=None, on_level=None, on_end=None, on_state=None):
        self.cfg = cfg
        self.q = queue.Queue()
        self.on_start = on_start or (lambda *_: None)
        self.on_level = on_level or (lambda *_: None)
        self.on_end = on_end or (lambda *_: None)
        self.on_state = on_state or (lambda *_: None)
        self.running = False
        self.durations = {}
        self._lock = threading.Lock()
        self._probe()

    def _probe(self):
        t = self.cfg["tts"]
        self.piper = C.which(t.get("piper_bin", "piper"))
        self.model = t.get("piper_model") or ""
        self.espeak = C.which(t.get("espeak_bin", "espeak-ng"))
        if self.piper and self.model and os.path.exists(self.model):
            self.engine = "piper"
        elif self.espeak:
            self.engine = "espeak"
        else:
            self.engine = "none"
        self.on_state("tts", f"mesin: {self.engine}")

    # ---------- API ----------
    def say(self, text, interrupt=True):
        text = clean(text)
        if text:
            self.q.put((text, interrupt))

    def say_later(self, delay, text):
        def _go():
            self.say(text)
        threading.Timer(delay, _go).start()

    def stop(self):
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._worker, daemon=True).start()

    # ---------- worker ----------
    def _worker(self):
        while self.running:
            try:
                text, interrupt = self.q.get(timeout=0.3)
            except queue.Empty:
                continue
            if not text:
                continue
            self.on_start(text)
            self._play(text)
            self.on_end(text)

    def _play(self, text):
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            if not _synth_to_wav(text, self.cfg, tmp.name):
                return
            samples, rate = _read_wav(tmp.name)
            if samples is None or len(samples) == 0:
                return
            dur = len(samples) / float(rate)
            self.durations[text] = dur
            self.on_level(0.0, dur)
            if not _play_samples(samples, rate, self.on_level):
                # fallback: tetap gerakkan mulut dari envelope amplitudo
                envelope = _envelope(samples, rate, 50.0)
                _play_with_aplay(tmp.name, envelope, self.on_level, dur)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


def clean(text):
    text = str(text).strip()
    text = re.sub(r"[*_`#]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _read_wav(path):
    try:
        with wave.open(path, "rb") as w:
            rate = w.getframerate()
            n = w.getnframes()
            raw = w.readframes(n)
            ch = w.getnchannels()
            width = w.getsampwidth()
        if width == 2:
            data = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        elif width == 4:
            data = np.frombuffer(raw, np.int32).astype(np.float32) / 2147483648.0
        else:
            data = np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0
            data /= 128.0
        if ch > 1:
            data = data.reshape(-1, ch).mean(axis=1)
        return data, rate
    except Exception:
        return None, 0


def _play_samples(samples, rate, on_level):
    """Putar via sounddevice sambil kirim level RMS (untuk animasi mulut)."""
    try:
        import sounddevice as sd
    except Exception:
        sd = None
    if sd is None:
        return False
    sr_out = int(rate)
    try:
        default_sr = sd.query_devices(kind="output")["default_samplerate"] or sr_out
    except Exception:
        default_sr = sr_out
    if abs(sr_out - default_sr) > 4000:
        target = int(default_sr)
        n = int(len(samples) * target / sr_out)
        if n > 0:
            idx = np.linspace(0, len(samples) - 1, n)
            samples = np.interp(idx, np.arange(len(samples)), samples).astype(np.float32)
            rate = target

    state = {"i": 0}
    block = 1024

    def cb(outdata, frames, t, status):
        i = state["i"]
        end = i + frames
        chunk = samples[i:end]
        if len(chunk) < frames:
            chunk = np.pad(chunk, (0, frames - len(chunk)))
        state["i"] = end
        outdata[:] = chunk.reshape(-1, 1)
        lvl = float(np.sqrt(np.mean(chunk ** 2)))
        on_level(min(1.0, lvl * 4.0), end / float(rate))

    try:
        with sd.OutputStream(samplerate=int(rate), blocksize=block, dtype="float32",
                             channels=1, callback=cb):
            n = int(np.ceil(len(samples) / block)) + 1
            for _ in range(n):
                if state["i"] >= len(samples):
                    break
                threading.Event().wait(block / float(rate))
        return True
    except Exception:
        return False


def _envelope(samples, rate, fps=50.0):
    """RMS per frame -> daftar level 0..1 untuk simulasi gerak mulut."""
    if samples is None or len(samples) == 0:
        return []
    win = max(1, int(rate / fps))
    n = len(samples) // win
    out = []
    for i in range(n):
        chunk = samples[i * win:(i + 1) * win]
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        out.append(min(1.0, rms * 4.0))
    return out


def _play_with_aplay(path, envelope=None, on_level=None, dur=0.0):
    player = C.which("paplay") or C.which("aplay") or C.which("ffplay") or C.which("afplay")
    if not player:
        return False
    args = [player, path]
    if player.endswith("aplay") and "ffplay" not in player:
        args = [player, "-q", path]
    elif "ffplay" in player:
        args = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", path]
    elif player.endswith("aplay"):
        args = [player, path]
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    step = 1.0 / 50.0
    i = 0
    while proc.poll() is None:
        if envelope and on_level:
            on_level(envelope[i] if i < len(envelope) else 0.0,
                     min(dur, i * step))
        i += 1
        time.sleep(step)
    proc.wait()
    return True