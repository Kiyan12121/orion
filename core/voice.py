"""Voice.

Speaking:  Microsoft neural voices via edge-tts (natural, free, needs internet). Audio is played
           by the interface, so the core reacts to the actual sound. If offline -> Windows voice.
           Replies are spoken sentence-by-sentence WHILE they're still being written (faster).
Listening: push-to-talk recording -> Groq Whisper.
"""
import asyncio
import base64
import io
import platform
import queue
import re
import subprocess
import threading
import uuid
import wave

IS_WIN = platform.system() == "Windows"

try:
    import numpy as np
except Exception:
    np = None
try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import edge_tts
except Exception:
    edge_tts = None


def speakable(text):
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"https?://\S+", "the link", t)
    t = re.sub(r"[*_#>|~]", "", t)
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()


class SentenceStream:
    """Feed it streamed text; it hands complete sentences (outside code blocks) to `say`."""
    END = re.compile(r"[.!?…](?=\s)|\n")

    def __init__(self, say):
        self.say = say
        self.text = ""
        self.pos = 0
        self.in_code = False
        self.spoke_any = False

    def feed(self, chunk):
        self.text += chunk
        self._drain(final=False)

    def flush(self):
        self._drain(final=True)
        return self.spoke_any

    def _emit(self, s):
        s = speakable(s)
        if len(re.sub(r"\W", "", s)) >= 2:
            self.say(s)
            self.spoke_any = True

    def _drain(self, final):
        while True:
            rest = self.text[self.pos:]
            if self.in_code:
                end = rest.find("```")
                if end == -1:
                    return
                self.pos += end + 3
                self.in_code = False
                continue
            fence = rest.find("```")
            seg = rest if fence == -1 else rest[:fence]
            if fence != -1:
                self._emit(seg)
                self._emit("The code's on screen.")
                self.pos += fence + 3
                self.in_code = True
                continue
            # speak up to the last sentence end (wait for ~40 chars so it sounds natural)
            ends = [m.end() for m in self.END.finditer(seg)]
            cut = None
            for e in ends:
                if e >= 40 or (final and e):
                    cut = e
            if final:
                cut = len(seg)
            if not cut:
                return
            self._emit(seg[:cut])
            self.pos += cut
            if final or self.pos >= len(self.text):
                return


class Speaker:
    def __init__(self, cfg, emit):
        self.cfg = cfg
        self.emit = emit                 # sends audio to the UI
        self.q = queue.Queue()
        self.gen = 0                     # bumps on stop() so queued speech is dropped
        self._offline = None
        self.neural_ok = edge_tts is not None
        self.making = False              # True while a sentence is being turned into audio
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def idle(self):
        return self.q.empty() and not self.making

    @property
    def enabled(self):
        return self.cfg["voice"].get("speak_replies", True) and self.cfg.get("theme") != "stealth"

    def say(self, text, voice=None, force=False):
        if (self.enabled or force) and text:
            self.q.put((self.gen, text, voice))

    def stop(self):
        self.gen += 1
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.emit("audio_stop")

    def _loop(self):
        while True:
            gen, text, voice = self.q.get()
            if gen != self.gen:
                continue
            self.making = True
            try:
                self._speak_one(gen, text, voice)
            finally:
                self.making = False

    def _speak_one(self, gen, text, voice):
        if True:
            v = self.cfg["voice"]
            if v.get("engine", "neural") == "neural" and self.neural_ok:
                try:
                    audio = asyncio.run(self._neural(text, voice or v.get("neural_voice", "en-GB-SoniaNeural"),
                                                     v.get("neural_rate", "+6%")))
                    if gen == self.gen and audio:
                        self.emit("audio", id=uuid.uuid4().hex[:8], text=text,
                                  data=base64.b64encode(audio).decode())
                    return
                except Exception:
                    pass          # offline or service hiccup -> fall through to Windows voice
            if gen == self.gen:
                self.offline_say(text)

    @staticmethod
    async def _neural(text, voice, rate):
        buf = bytearray()
        async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
            if chunk["type"] == "audio":
                buf += chunk["data"]
        return bytes(buf)

    def offline_say(self, text):
        """Windows built-in voice (used offline or if the UI can't play audio)."""
        self.emit("speaking", on=True)
        try:
            if self._offline is None:
                try:
                    if IS_WIN:
                        import pythoncom
                        pythoncom.CoInitialize()
                    import pyttsx3
                    eng = pyttsx3.init()
                    eng.setProperty("rate", self.cfg["voice"].get("offline_rate", 180))
                    for vv in eng.getProperty("voices"):        # prefer a female voice
                        if any(n in (vv.name or "").lower() for n in ("hazel", "zira", "susan", "female")):
                            eng.setProperty("voice", vv.id)
                            break
                    self._offline = eng
                except Exception:
                    self._offline = False
            if self._offline:
                self._offline.say(text)
                self._offline.runAndWait()
            elif IS_WIN:
                safe = text.replace("'", "''")
                subprocess.run(["powershell", "-NoProfile", "-Command",
                                "Add-Type -AssemblyName System.Speech;"
                                "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('" + safe + "')"],
                               creationflags=0x08000000)
        except Exception:
            pass
        self.emit("speaking", on=False)


class Recorder:
    """Push-to-talk: start() then stop() -> WAV bytes."""
    RATE = 16000

    def __init__(self):
        self.frames = []
        self.stream = None

    @property
    def available(self):
        return sd is not None

    @property
    def recording(self):
        return self.stream is not None

    def start(self):
        if sd is None:
            raise RuntimeError("Microphone support isn't installed (sounddevice).")
        self.frames = []
        self.stream = sd.InputStream(samplerate=self.RATE, channels=1, dtype="int16",
                                     callback=lambda data, *_: self.frames.append(data.copy()))
        self.stream.start()

    def level(self):
        if not self.frames:
            return 0.0
        return float(min(1.0, np.abs(self.frames[-1]).mean() / 3000))

    def stop(self):
        if not self.stream:
            return b""
        self.stream.stop()
        self.stream.close()
        self.stream = None
        if not self.frames:
            return b""
        audio = np.concatenate(self.frames)
        if len(audio) < self.RATE * 0.4:
            return b""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.RATE)
            w.writeframes(audio.tobytes())
        return buf.getvalue()
