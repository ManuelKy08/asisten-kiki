"""STT streaming offline (Vosk) + wake word + VAD sederhana.

Model Indonesia: `vosk.Model(lang="id-small")` (auto-download ~50MB ke ~/.cache/vosk)
Alternatif pip: pip install vosk  (model penuh: https://alphacephei.com/vosk/models)
"""
import json
import queue
import re
import threading
import time

import numpy as np

try:                                    # hanya perlu saat mikrofon hidup
    import sounddevice as sd
except Exception:                       # noqa: BLE001
    sd = None


class STT:
    def __init__(self, cfg, on_text, on_state=None):
        self.cfg = cfg["stt"]
        self.on_text = on_text
        self.on_state = on_state or (lambda *_: None)
        self.name = cfg["assistant"]["name"]
        self.sr = int(self.cfg["sample_rate"])
        self.q = queue.Queue()
        self.model = None
        self.rec = None
        self.armed = not self.cfg.get("require_wake", True)
        self.last_partial = ""
        self.running = False
        self.muted = False
        self._device = None

    # ---------- wake word ----------
    def _wake_patterns(self):
        words = [w.strip().lower() for w in self.cfg.get("wake_words", []) if w.strip()]
        words += [self.name.lower()]
        words = sorted(set(words), key=len, reverse=True)
        return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b")

    def strip_wake(self, text):
        return self._wake_patterns().sub(" ", text).strip(" ,.!?-")

    def has_wake(self, text):
        return bool(self._wake_patterns().search(text.lower()))

    # ---------- audio ----------
    def _pick_device(self):
        if sd is None:
            return None
        want = (self.cfg.get("device") or "").strip()
        if want:
            return want
        try:
            infos = sd.query_devices()
            best = None
            for i, d in enumerate(infos):
                if d.get("max_input_channels", 0) < 1:
                    continue
                name = (d.get("name") or "").lower()
                score = 0
                if any(k in name for k in ("mic", "usb", "audio", "input", "headset")):
                    score += 5
                if any(k in name for k in ("webcam", "camera", "bluetooth")):
                    score -= 3  # mic internal laptops sering jelek
                if d.get("default_samplerate") in (None, 0, self.sr):
                    score += 1
                if best is None or score > best[0]:
                    best = (score, d["name"])
            return best[1] if best else None
        except Exception:
            return None

    def _callback(self, indata, frames, t, status):
        if status:
            self.on_state("warn", str(status))
        if self.muted:
            return
        self.q.put(bytes(indata))

    def start(self):
        if sd is None:
            raise RuntimeError("sounddevice belum terpasang: pip install sounddevice")
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)
        model_path = (self.cfg.get("model") or "").strip()
        self.on_state("loading", "memuat model suara")
        self.model = Model(model_path) if model_path else Model(lang="id-small")
        self.rec = __import__("vosk").KaldiRecognizer(self.model, self.sr)
        self._device = self._pick_device()
        self.running = True
        threading.Thread(target=self._mic_thread, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        self.on_state("ready", f"mic: {self._device}")

    def _mic_thread(self):
        if sd is None:
            self.on_state("error", "sounddevice tidak tersedia")
            return
        try:
            with sd.RawInputStream(
                samplerate=self.sr, blocksize=int(self.sr * 0.1), dtype="int16",
                channels=1, device=self._device, callback=self._callback,
            ):
                while self.running:
                    time.sleep(0.2)
        except Exception as e:
            self.on_state("error", f"mic gagal: {e}")

    # ---------- worker ----------
    def _worker(self):
        gate = float(self.cfg.get("mic_rms_gate", 0.006))
        silence = self.cfg.get("silence_ms", 1100) / 1000.0
        max_t = self.cfg.get("max_utterance_s", 15)
        armed_at = time.time() if self.armed else 0.0
        buf, started = [], None

        while self.running:
            try:
                data = self.q.get(timeout=0.2)
            except queue.Empty:
                if buf and (time.time() - started) > silence:
                    self._flush(buf, gate)
                    buf, started = [], None
                    self.armed = not self.cfg.get("require_wake", True)
                    armed_at = 0.0
                continue

            rms = float(np.sqrt(np.mean(np.frombuffer(data, np.int16, dtype=np.int16) ** 2))) / 32768.0
            self.on_state("level", rms)

            if rms < gate:
                if buf and (time.time() - started) > silence:
                    self._flush(buf, gate)
                    buf, started = [], None
                continue

            res = json.loads(self.rec.AcceptWaveform(data) or "{}")
            text = (res.get("text") or "").strip()
            if text:
                self._handle_text(text)

            part = json.loads(self.rec.PartialResult() or "{}").get("partial", "").strip()
            if part != self.last_partial:
                self.last_partial = part
                self.on_state("partial", part)
                if not self.armed and self.has_wake(part):
                    self.armed, armed_at = True, time.time()
                    self.on_state("wake", part)

            if self.armed:
                started = started or time.time()
                buf.append(data)
                if time.time() - armed_at > max_t + 3 or len(buf) * 0.1 > max_t:
                    self._flush(buf, gate)
                    buf, started = [], None
                    self.armed = not self.cfg.get("require_wake", True)

    def _flush(self, buf, gate):
        raw = b"".join(buf)
        if not raw:
            return
        buf.clear()
        rms = float(np.sqrt(np.mean(np.frombuffer(raw, np.int16, dtype=np.int16) ** 2))) / 32768.0
        if rms < gate:
            return
        self.rec.AcceptWaveform(raw)
        res = json.loads(self.rec.FinalResult() or "{}")
        text = (res.get("text") or "").strip()
        if text:
            self._handle_text(text, final=True)

    def _handle_text(self, text, final=False):
        low = text.lower()
        if self.cfg.get("require_wake", True):
            if not self.armed:
                if self.has_wake(low):
                    self.armed = True
                    text = self.strip_wake(low)
                else:
                    return  # abaikan, belum diaktifkan
        cmd = self.strip_wake(low)
        if final and len(cmd.split()) < int(self.cfg.get("min_words", 1)):
            self.armed = False
            return
        self.on_state("armed" if self.armed else "idle", cmd)
        self.on_text(text)
        if final:
            self.armed = False

    # ---------- kontrol ----------
    def force_arm(self):
        self.armed = True
        self.on_state("wake", "manual")

    def mute(self, m=True):
        self.muted = m

    def stop(self):
        self.running = False