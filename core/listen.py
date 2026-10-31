"""Hands-free listening.

Wake word: openWakeWord runs offline on the CPU (~3-5% of one core). Built-in phrase: "Hey Jarvis"
(a custom "Hey ORION" model can be trained for free later and dropped into data/wakeword/).
After the wake word ORION chimes, records until you stop talking, transcribes and acts.

Voice ID (optional, PC only): learns your voice from a few short recordings and ignores other people.
Both need the extras from 4_INSTALL_VOICE_EXTRAS.bat.
"""
import io
import os
import threading
import time
import wave

from .paths import DATA_DIR

try:
    import numpy as np
except Exception:
    np = None
try:
    import sounddevice as sd
except Exception:
    sd = None

RATE = 16000


def extras_status():
    """None = working, otherwise the exact reason it isn't (shown in Devices)."""
    import sys
    from .paths import FROZEN
    out = {"python": sys.executable, "frozen": FROZEN}
    if FROZEN:
        why = "ORION.exe can't use the voice extras — launch ORION from the Desktop shortcut instead."
        out.update(wake=why, voice_id=why)
        return out
    try:
        import openwakeword  # noqa: F401
        out["wake"] = None if sd is not None else "microphone library (sounddevice) missing"
    except Exception as e:
        out["wake"] = f"{type(e).__name__}: {e}"
    try:
        import resemblyzer  # noqa: F401
        out["voice_id"] = None
    except Exception as e:
        out["voice_id"] = f"{type(e).__name__}: {e}"
    return out
PRINT_PATH = os.path.join(DATA_DIR, "voiceprint.npy")
WAKE_DIR = os.path.join(DATA_DIR, "wakeword")


def to_wav(audio):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.astype("int16").tobytes())
    return buf.getvalue()


def record_until_silence(stream_read, max_s=12, silence_s=1.1, start_timeout=4):
    """Reads 80ms frames until the speaker stops. Returns int16 numpy audio (or empty)."""
    frames, spoken, quiet, t0 = [], False, 0.0, time.time()
    floor = []
    while time.time() - t0 < max_s:
        f = stream_read()
        frames.append(f)
        lvl = float(np.abs(f).mean())
        if len(floor) < 4:                 # first ~0.3s = background noise level
            floor.append(lvl)
        loud = lvl > max(350, min(floor) * 3)
        if loud:
            spoken, quiet = True, 0.0
        elif spoken:
            quiet += len(f) / RATE
            if quiet >= silence_s:
                break
        elif time.time() - t0 > start_timeout:
            return np.zeros(0, dtype="int16")
    return np.concatenate(frames) if frames and spoken else np.zeros(0, dtype="int16")


class VoiceID:
    def __init__(self, cfg):
        self.cfg = cfg
        self.enc = None
        self.print = np.load(PRINT_PATH) if (np is not None and os.path.exists(PRINT_PATH)) else None

    @property
    def available(self):
        return extras_status()["voice_id"] is None

    def _encoder(self):
        if self.enc is None:
            from resemblyzer import VoiceEncoder
            self.enc = VoiceEncoder("cpu", verbose=False)
        return self.enc

    def embed(self, audio):
        from resemblyzer import preprocess_wav
        wav = preprocess_wav(audio.astype("float32") / 32768.0, source_sr=RATE)
        return self._encoder().embed_utterance(wav)

    def enroll(self, clips):
        embs = [self.embed(c) for c in clips if len(c) > RATE]
        if not embs:
            raise RuntimeError("Recordings were too short.")
        e = np.mean(embs, axis=0)
        self.print = e / np.linalg.norm(e)
        np.save(PRINT_PATH, self.print)
        return True

    def score(self, audio):
        if self.print is None:
            return 1.0
        e = self.embed(audio)
        return float(np.dot(e / np.linalg.norm(e), self.print))

    def is_owner(self, audio):
        if not self.cfg.get("voice_id", {}).get("enabled") or self.print is None or not self.available:
            return True
        try:
            return self.score(audio) >= float(self.cfg["voice_id"].get("threshold", 0.72))
        except Exception:
            return True


class WakeListener:
    def __init__(self, cfg, on_command, emit, voice_id, busy=lambda: False):
        self.cfg = cfg
        self.on_command = on_command      # on_command(wav_bytes)
        self.emit = emit
        self.voice_id = voice_id
        self.busy = busy                  # True while push-to-talk is recording / ORION speaking
        self.running = False
        self.error = None
        self._thread = None

    @property
    def available(self):
        return extras_status()["wake"] is None

    def start(self):
        if self.running or not self.available:
            return False
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self.running = False

    def _model(self):
        import openwakeword
        from openwakeword.model import Model
        name = self.cfg.get("wake", {}).get("model", "hey_jarvis")
        custom = os.path.join(WAKE_DIR, name + ".onnx")
        if os.path.exists(custom):
            return Model(wakeword_models=[custom], inference_framework="onnx")
        try:
            openwakeword.utils.download_models([name])
        except Exception:
            pass
        return Model(wakeword_models=[name], inference_framework="onnx")

    def _loop(self):
        try:
            model = self._model()
        except Exception as e:
            self.error = f"wake word model failed: {e}"
            self.running = False
            self.emit("toast", level="warn", text=self.error)
            return
        thr = float(self.cfg.get("wake", {}).get("sensitivity", 0.5))
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=1280) as st:
            read = lambda: st.read(1280)[0][:, 0].copy()
            cool = 0
            while self.running:
                frame = read()
                if self.busy():
                    continue
                scores = model.predict(frame)
                if cool > 0:
                    cool -= 1
                    continue
                if max(scores.values() or [0]) >= thr:
                    model.reset()
                    cool = 25
                    self.emit("wake")
                    self.emit("state", state="listening")
                    audio = record_until_silence(read)
                    self.emit("state", state="idle")
                    if len(audio) < RATE * 0.4:
                        continue
                    if not self.voice_id.is_owner(audio):
                        self.emit("toast", level="warn", text="Voice not recognised — ignored.")
                        continue
                    threading.Thread(target=self.on_command, args=(to_wav(audio),), daemon=True).start()
