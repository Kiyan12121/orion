"""ORION's ears: talk as long as you like, and ORION works out when you've finished.

How it knows you're done ("smart end-of-turn"):
  1. A voice detector tracks the room's background noise and spots when you're actually talking.
  2. When you pause (~0.8s), ORION quietly transcribes what you've said so far (it keeps listening).
  3. If it sounds finished ("…and turn on gaming mode.") it stops. If it sounds mid-thought
     ("open Spotify and…", "um", "because"), it waits for a longer pause (~2.5s) instead.
  4. Saying "send it" or "over" at the end sends straight away. Tapping the mic also sends.

Also: conversation mode (after ORION answers, it listens for your follow-up without a wake word),
barge-in (start talking while ORION is speaking to interrupt it), and clean-up of the audio
(trims silence, evens out volume, tells Whisper the names you use) for better accuracy.
"""
import io
import re
import threading
import time
import wave

try:
    import numpy as np
except Exception:
    np = None
try:
    import sounddevice as sd
except Exception:
    sd = None

RATE = 16000
FRAME = 480                       # 30 ms
PATIENCE = {                      # (short pause -> check, long pause -> give up waiting, hard stop secs)
    "quick":   (0.6, 1.8),
    "normal":  (0.8, 2.6),
    "relaxed": (1.1, 3.6),
}
TRAILING = set("""and or but so because cause cuz the a an to of for with my your our his her their is are was were
be been am i i'm im we you they it it's its that this these those which who what when where if then than as at in
on by from into about also plus like um uh erm er hmm mm maybe can could should would will just gonna wanna gotta
need want please also and,""".split())
SHORT_OK = set("""yes yeah yep no nope nah ok okay thanks cheers stop cancel pause play next skip back louder quieter
mute unmute hello hi hey morning evening goodbye bye sure done right left up down""".split())
SEND_WORDS = re.compile(r"[\s,.]*(send it|over and out|over|that's it|that is it|go ahead)[.!]*\s*$", re.I)
END_CONVO = re.compile(r"^\s*(thanks?( you)?|cheers|that'?s all|that will be all|nothing( else)?|no thanks|goodbye|bye|"
                       r"stop listening|i'?m good|all good|never ?mind)[.! ]*(orion|jarvis)?[.! ]*$", re.I)


def sounds_unfinished(text):
    """Does this transcript sound like the speaker is mid-sentence?"""
    t = (text or "").strip()
    if not t:
        return True
    if re.search(r"(,|\.\.\.|…|-|—|:)\s*$", t):
        return True
    words = re.findall(r"[a-z']+", t.lower())
    if not words:
        return True
    if words[-1] in TRAILING:
        return True
    if len(words) == 1 and words[0] not in SHORT_OK:
        return True
    return False


def to_wav(audio):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.astype("int16").tobytes())
    return buf.getvalue()


def clean(audio, speech_start=None):
    """Trim leading/trailing silence (keeping a little) and even out the volume."""
    if audio is None or not len(audio):
        return audio
    a = audio.astype("float32")
    if speech_start is not None:
        a = a[max(0, speech_start - int(RATE * 0.25)):]
    env = np.abs(a)
    loud = np.where(env > max(300.0, float(np.percentile(env, 60)) * 2))[0]
    if len(loud):
        a = a[:min(len(a), loud[-1] + int(RATE * 0.35))]
    peak = float(np.max(np.abs(a))) if len(a) else 0
    if 300 < peak < 20000:                       # quiet mic -> boost to about -3 dB
        a = a * min(8.0, 23000 / peak)
    return np.clip(a, -32767, 32767).astype("int16")


class VAD:
    """Voice detector that copes with music and background noise.

    - Looks at the speech band (300-3400 Hz), so bass and drums matter much less.
    - The 'background level' is learned from ALL recent sound (rolling 4 s), so a song playing in the
      room quickly becomes the background instead of counting as you talking forever.
    - Speech goes up and down (syllables); steady sound like music doesn't, which also helps.
    """

    def __init__(self, sensitivity=1.0):
        self.sens = max(0.4, min(2.0, sensitivity))
        self.window = []          # recent speech-band levels (all frames)
        self.floor = None
        self.run = 0
        self.steady = 0           # frames of loud-but-steady sound (music / fan)
        self.cvs = []             # how much the background normally wobbles

    @staticmethod
    def band(f):
        x = f.astype("float32")
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        freqs = np.fft.rfftfreq(len(x), 1 / RATE)
        b = spec[(freqs >= 300) & (freqs <= 3400)]
        return float(np.sqrt(np.mean(b ** 2)) / 8 + 1e-6)

    def level(self, f):
        return float(np.sqrt(np.mean(f.astype("float32") ** 2)) + 1e-6)

    def is_speech(self, f):
        lv = self.band(f)
        self.window.append(lv)
        self.window = self.window[-133:]                       # ~4 s
        if len(self.window) >= 8:
            self.floor = float(np.percentile(self.window, 15))
        elif self.floor is None or lv < self.floor:
            self.floor = lv
        base = max(160.0 / self.sens, self.floor)
        recent = np.array(self.window[-20:])                    # ~0.6 s
        cv = float(np.std(recent) / (np.mean(recent) + 1e-6)) if len(recent) >= 10 else 1.0
        if lv > base * (2.8 / self.sens) and lv > 160.0 / self.sens:
            speech = cv > 0.15 or lv > base * 6                 # loud and wobbly = voice; loud and steady = music
        else:                                                   # quieter than that: voice over music wobbles more than the music does
            calm = float(np.median(self.cvs)) if len(self.cvs) >= 20 else 0.2
            speech = self.floor > 300 and lv > base * (1.2 / self.sens) and cv > max(0.16, calm * 1.45)
        if not speech:
            self.cvs.append(cv)
            self.cvs = self.cvs[-150:]
        self.steady = self.steady + 1 if (lv > base * 1.3 and cv <= 0.15) else 0
        self.run = self.run + 1 if speech else 0
        return speech, self.level(f)


HALLUCINATIONS = {"thank you", "thanks for watching", "thank you for watching", "you", "bye", "music",
                  "subtitles by the amara org community", "please subscribe", "so", "uh", "um", ""}


def junk(text, seconds):
    """Whisper sometimes 'hears' these in music or silence."""
    t = re.sub(r"[^a-z ]", "", (text or "").lower()).strip()
    if "♪" in (text or "") or re.fullmatch(r"[\W_]*", text or ""):
        return True
    return t in HALLUCINATIONS and seconds > 4


class Ears:
    """One mic session at a time. listen() blocks and returns the transcript ('' if nothing)."""

    def __init__(self, cfg, emit, transcriber, voice_id=None):
        self.cfg = cfg
        self.emit = emit
        self.transcriber = transcriber    # function(wav_bytes, prompt) -> text
        self.voice_id = voice_id
        self.active = False
        self.level = 0.0
        self._force = threading.Event()
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    @property
    def available(self):
        return sd is not None and np is not None

    @property
    def vc(self):
        v = self.cfg.setdefault("voice", {})
        v.setdefault("patience", "normal")
        v.setdefault("conversation", True)
        v.setdefault("barge_in", False)
        v.setdefault("mic_sensitivity", 1.0)
        v.setdefault("max_talk_seconds", 300)
        return v

    def vocab(self):
        """Names Whisper should expect — makes 'Hatchlands', 'Root', friends' names come out right."""
        words = ["ORION", self.cfg.get("owner_name", "Kiyan"), "Root", "Hatchlands", "Roblox", "Tailscale",
                 "Night Shift", "Autopilot", "GCSE"]
        mem = None
        try:
            from .tools import CTX
            mem = CTX.get("memory")
        except Exception:
            pass
        if mem:
            for f in mem.facts[-80:]:
                if f.get("cat") in ("person", "project"):
                    words += re.findall(r"\b[A-Z][a-zA-Z0-9]{2,}\b", f["text"])
        seen, out = set(), []
        for w in words:
            if w.lower() not in seen:
                seen.add(w.lower())
                out.append(w)
        return ", ".join(out[:40]) + "."

    def finish(self):
        """User tapped the mic again — send what we have now."""
        self._force.set()

    def cancel(self):
        self._cancel.set()

    def _hear(self, audio, start):
        wav = to_wav(clean(audio, start))
        return (self.transcriber(wav, self.vocab()) or "").strip()

    def listen(self, start_timeout=8.0, purpose="command"):
        """Record until the user finishes. Returns text ('' = nothing heard / cancelled)."""
        if not self.available:
            raise RuntimeError("Microphone support isn't installed (sounddevice).")
        if not self._lock.acquire(blocking=False):
            return ""
        self.active = True
        self._force.clear()
        self._cancel.clear()
        short, long_ = PATIENCE.get(self.vc["patience"], PATIENCE["normal"])
        max_s = float(self.vc.get("max_talk_seconds", 180))
        vad = VAD(float(self.vc.get("mic_sensitivity", 1.0)))
        frames, spoke_at, speech_frames, quiet, t0 = [], None, 0, 0.0, time.time()
        partial, partial_len, checking, checked_pause = "", 0, None, False
        nonstop = 0.0           # seconds of sound with no pause at all (music?)
        recent_sp = []
        result = {"text": None}
        try:
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME) as st:
                for _ in range(5):                 # first 150 ms: learn the background noise
                    f = st.read(FRAME)[0][:, 0].copy()
                    vad.is_speech(f)
                    frames.append(f)
                while True:
                    if self._cancel.is_set():
                        return ""
                    f = st.read(FRAME)[0][:, 0].copy()
                    frames.append(f)
                    speech, lv = vad.is_speech(f)
                    self.level = min(1.0, lv / 2500)
                    n = len(frames) * FRAME
                    recent_sp = (recent_sp + [speech])[-10:]
                    if speech and sum(recent_sp) >= 5 and spoke_at is None:      # 5 of the last 10 frames
                        spoke_at = max(0, n - FRAME * 6)
                    if spoke_at is None:
                        if self._force.is_set() or time.time() - t0 > start_timeout:
                            return ""
                        continue
                    if speech:
                        speech_frames += 1
                        quiet = 0.0
                        nonstop += FRAME / RATE
                        checked_pause = False
                        if checking:                       # they carried on talking — ignore that check
                            checking = None
                    else:
                        quiet += FRAME / RATE
                        if quiet > 0.25:
                            nonstop = 0.0
                    talked = speech_frames * FRAME / RATE
                    # nobody talks for 14 s without a breath — check the last few seconds really are words
                    if nonstop > 14 and checking is None:
                        nonstop = 0.0
                        tail = np.concatenate(frames[-int(RATE * 6 / FRAME):])
                        try:
                            heard = (self.transcriber(to_wav(clean(tail)), self.vocab()) or "").strip()
                        except Exception:
                            heard = "x"
                        if junk(heard, 6):
                            self.emit("toast", level="warn", text="That sounds like music, not you — stopping.")
                            break
                    if self._force.is_set() or n / RATE > max_s:
                        break
                    # short pause: quietly check if it sounds finished (keeps recording meanwhile)
                    if quiet >= short and talked > 0.35 and checking is None and not checked_pause:
                        checked_pause = True
                        snap, snap_n = np.concatenate(frames), n
                        full = snap_n - spoke_at <= RATE * 15      # long talk: only check how it ENDS
                        checking = {"n": snap_n, "done": False, "text": "", "full": full}
                        c = checking

                        def run(c=c, snap=snap, full=full):
                            try:
                                c["text"] = self._hear(snap, spoke_at) if full else self._hear(snap[-RATE * 8:], None)
                            except Exception as e:
                                c["text"] = ""
                                c["err"] = str(e)
                            c["done"] = True
                        threading.Thread(target=run, daemon=True).start()
                    if checking and checking["done"]:
                        partial, partial_len, checking_full = checking["text"], checking["n"], checking["full"]
                        checking = None
                        if partial and junk(partial, (partial_len - (spoke_at or 0)) / RATE):
                            partial = ""
                        if partial:
                            self.emit("hearing", text=partial if checking_full else "…" + partial)
                        done_now = partial and (SEND_WORDS.search(partial) or not sounds_unfinished(partial))
                        if done_now:
                            if checking_full:
                                result["text"] = SEND_WORDS.sub("", partial).strip()
                            break
                    if quiet >= long_:
                        break
            audio = np.concatenate(frames)
            if result["text"] is not None and partial_len >= len(audio) - int(RATE * (long_ + 0.5)):
                text = result["text"]
                if junk(text, partial_len / RATE):
                    return ""
            elif speech_frames * FRAME / RATE < 0.3:
                return ""
            else:
                if self.voice_id and purpose == "wake" and not self.voice_id.is_owner(audio):
                    self.emit("toast", level="warn", text="Voice not recognised — ignored.")
                    return ""
                self.emit("state", state="thinking")
                text = self._hear(audio, spoke_at)
                text = SEND_WORDS.sub("", text).strip() if SEND_WORDS.search(text or "") else text
                if junk(text, len(audio) / RATE):
                    return ""
            return text or ""
        finally:
            self.active = False
            self.level = 0.0
            self._lock.release()

    def wait_for_voice(self, stop, threshold=4.0, need=0.35):
        """Barge-in helper: returns True when the user starts talking (louder than ORION's own echo)."""
        if not self.available:
            return False
        vad = VAD(1.0)
        run = 0
        try:
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME) as st:
                for _ in range(10):
                    vad.is_speech(st.read(FRAME)[0][:, 0].copy())
                base = vad.floor or 300
                while not stop():
                    lv = vad.band(st.read(FRAME)[0][:, 0].copy())
                    run = run + 1 if lv > max(600, base * threshold) else 0
                    if run * FRAME / RATE >= need:
                        return True
        except Exception:
            return False
        return False
