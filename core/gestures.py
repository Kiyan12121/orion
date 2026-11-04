"""Hand gestures through the webcam — strictly opt-in, off by default, never records or saves a frame.

wave        → wake ORION (start listening)
swipe ←/→   → previous / next page
open palm   → stop talking / stop the task
pinch       → close the top pop-up

Uses MediaPipe Hands when it's installed (accurate: palm, pinch, swipe, wave). If only OpenCV is
available it falls back to simple motion tracking (swipe and wave only). The UI shows a camera light
the whole time the camera is on."""
import logging
import threading
import time

log = logging.getLogger("orion")


def available():
    out = {"cv2": False, "mediapipe": False}
    try:
        import cv2  # noqa: F401
        out["cv2"] = True
    except Exception:
        pass
    try:
        import mediapipe  # noqa: F401
        out["mediapipe"] = True
    except Exception:
        pass
    return out


MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"


def _hand_detector():
    """Returns fn(rgb_frame) -> list of 21 landmarks (.x/.y) or None. Works on old MediaPipe (solutions)
    and new MediaPipe (tasks API, model downloaded once to data/)."""
    import mediapipe as mp
    if hasattr(mp, "solutions"):
        hands = mp.solutions.hands.Hands(max_num_hands=1, model_complexity=0, min_detection_confidence=.6, min_tracking_confidence=.5)

        def old(rgb):
            r = hands.process(rgb)
            return r.multi_hand_landmarks[0].landmark if r.multi_hand_landmarks else None
        return old
    import os
    import requests
    from mediapipe.tasks.python import BaseOptions, vision
    from .paths import DATA_DIR
    path = os.path.join(DATA_DIR, "hand_landmarker.task")
    if not os.path.exists(path) or os.path.getsize(path) < 100000:
        r = requests.get(MODEL_URL, timeout=60)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    det = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=path), num_hands=1, running_mode=vision.RunningMode.IMAGE,
        min_hand_detection_confidence=.6))

    def new(rgb):
        r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        return r.hand_landmarks[0] if r.hand_landmarks else None
    return new


class CamLost(Exception):
    pass


class PhoneCam:
    """Frames pushed by the phone app ("ORION's eyes") look like a normal OpenCV camera."""
    def __init__(self):
        self.jpg, self.t, self.seq, self.used = None, 0, 0, 0
        self.cv = threading.Condition()

    def push(self, raw):
        with self.cv:
            self.jpg, self.t, self.seq = raw, time.time(), self.seq + 1
            self.cv.notify_all()

    def live(self):
        return time.time() - self.t < 3

    def isOpened(self):
        return True

    def set(self, *a):
        return True

    def release(self):
        pass

    def read(self):
        import cv2
        import numpy as np
        with self.cv:
            self.cv.wait_for(lambda: self.seq != self.used, timeout=1.5)
            if time.time() - self.t > 5:
                raise CamLost("phone camera stopped")
            if self.seq == self.used:
                return False, None
            self.used, raw = self.seq, self.jpg
        f = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        return f is not None, f


PHONE = PhoneCam()


class Gestures:
    COOLDOWN = 1.4

    def __init__(self, cfg, emit):
        self.cfg, self.emit = cfg, emit
        self.on = False
        self.mode = ""
        self.err = ""
        self.cam = None
        self._stop = threading.Event()
        self._t = None
        self._last = 0
        if self.gc.get("enabled"):
            self.start()

    @property
    def gc(self):
        return self.cfg.setdefault("gestures", {"enabled": False, "camera": 0})

    # ------------------------------------------------------------------ control
    def start(self):
        if self._t and self._t.is_alive():
            return True
        self.err = ""
        av = available()
        if not av["cv2"]:
            self.err = "Needs OpenCV — press INSTALL on the gestures card."
            return False
        self._stop.clear()
        self._t = threading.Thread(target=self._run, args=(av["mediapipe"],), daemon=True)
        self._t.start()
        return True

    def stop(self):
        self._stop.set()

    def _fire(self, g, **d):
        now = time.time()
        if now - self._last < self.COOLDOWN:
            return
        from .tools import CTX
        gm = CTX.get("gaming")
        if gm and gm.active:                     # never interfere with a game
            return
        self._last = now
        log.info("gesture: %s", g)
        self.emit("gesture", g=g, **d)

    # ------------------------------------------------------------------ camera loop
    def _open(self, cv2):
        """Finds a camera that actually gives frames: tries the saved one first, then cameras 0-5 on every
        Windows backend (virtual cameras like Iriun, DroidCam and OBS often sit on 1 or 2, or only work on one backend)."""
        backs = [b for b in (getattr(cv2, "CAP_DSHOW", None), getattr(cv2, "CAP_MSMF", None), getattr(cv2, "CAP_ANY", 0)) if b is not None]
        saved = (int(self.gc.get("camera", 0)), self.gc.get("backend"))
        tries = ([saved] if saved[1] is not None else []) + [(i, b) for i in range(6) for b in backs]
        seen = set()
        for i, b in tries:
            if (i, b) in seen or self._stop.is_set():
                continue
            seen.add((i, b))
            try:
                cap = cv2.VideoCapture(i, b)
                if not cap or not cap.isOpened():
                    continue
                ok = False
                for _ in range(15):                  # virtual cams can take a moment to send the first frame
                    ok, f = cap.read()
                    if ok and f is not None and f.size:
                        break
                    time.sleep(.1)
                if ok:
                    self.gc["camera"], self.gc["backend"] = i, b
                    log.info("gestures: camera %s backend %s", i, b)
                    try:
                        from . import config
                        config.save(self.cfg)
                    except Exception:
                        pass
                    return cap, i
                cap.release()
            except Exception:
                continue
        return None, None

    def waiting(self):
        return bool(self._t and self._t.is_alive() and not self.on)

    def _run(self, use_mp):
        """Runs until switched off. Uses the phone's camera whenever it's streaming, otherwise a webcam;
        with neither it waits (re-scanning webcams every 30s) instead of giving up."""
        import cv2
        scanned = 0
        told = False
        while not self._stop.is_set():
            cap, idx = None, None
            if PHONE.live():
                cap, idx = PHONE, "phone"
            elif time.time() - scanned > 30:
                scanned = time.time()
                cap, idx = self._open(cv2)
            if cap is None:
                if not told:
                    self.err = ("Waiting for a camera — on your phone open PC › ORION'S EYES and tap START CAMERA "
                                "(or start Iriun / plug in a webcam).")
                    self.emit("gesture_state", on=False, err=self.err)
                    told = True
                self._stop.wait(1)
                continue
            told = False
            self.cam = idx
            if cap is not PHONE:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            self.on, self.err = True, ""
            self.mode = "mediapipe" if use_mp else "motion"
            self.emit("gesture_state", on=True, mode=self.mode)
            try:
                (self._loop_mp if use_mp else self._loop_motion)(cap, cv2)
            except CamLost:
                scanned = 0
            except Exception as e:
                self.err = str(e)
                log.exception("gestures")
                self._stop.wait(5)
            finally:
                cap.release()
                self.on = False
                self.emit("gesture_state", on=False, err=self.err)
        self.on = False

    def _loop_mp(self, cap, cv2):
        detect = _hand_detector()
        track = []                                   # (t, x) of the wrist
        palm_since = None
        bad = 0
        while not self._stop.is_set():
            ok, frame = cap.read()
            if cap is not PHONE and PHONE.live():
                raise CamLost("phone camera took over")
            if not ok:
                bad += 1
                if bad > 25:
                    raise CamLost("camera stopped")
                time.sleep(.2)
                continue
            bad = 0
            if frame.shape[1] > 480:
                frame = cv2.resize(frame, (320, int(320 * frame.shape[0] / frame.shape[1])))
            lm = detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            now = time.time()
            if not lm:
                track, palm_since = [], None
                time.sleep(.05)
                continue
            x = 1 - lm[0].x                              # mirror so "right" means the user's right
            track = [p for p in track if now - p[0] < .8] + [(now, x)]
            # pinch: thumb tip close to index tip
            size = abs(lm[0].y - lm[9].y) + 1e-6
            pinch = ((lm[4].x - lm[8].x) ** 2 + (lm[4].y - lm[8].y) ** 2) ** .5 / size
            fingers = sum(lm[t].y < lm[t - 2].y for t in (8, 12, 16, 20))
            if pinch < .25 and fingers <= 2:
                self._fire("pinch")
                track = []
            elif fingers == 4 and len(track) > 3 and max(p[1] for p in track) - min(p[1] for p in track) < .05:
                palm_since = palm_since or now
                if now - palm_since > .7:
                    self._fire("palm")
                    palm_since = None
            else:
                palm_since = None
            self._motion(track, now)
            time.sleep(.03)

    def _loop_motion(self, cap, cv2):
        prev, track = None, []
        bad = 0
        while not self._stop.is_set():
            ok, frame = cap.read()
            if cap is not PHONE and PHONE.live():
                raise CamLost("phone camera took over")
            if not ok:
                bad += 1
                if bad > 25:
                    raise CamLost("camera stopped")
                time.sleep(.2)
                continue
            bad = 0
            if frame.shape[1] > 480:
                frame = cv2.resize(frame, (320, int(320 * frame.shape[0] / frame.shape[1])))
            g = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
            now = time.time()
            if prev is not None:
                d = cv2.threshold(cv2.absdiff(prev, g), 25, 255, cv2.THRESH_BINARY)[1]
                m = cv2.moments(d)
                area = m["m00"] / 255 / (d.shape[0] * d.shape[1])
                if .02 < area < .4:
                    track = [p for p in track if now - p[0] < .8] + [(now, 1 - m["m10"] / m["m00"] / d.shape[1])]
                else:
                    track = [p for p in track if now - p[0] < .8]
                self._motion(track, now)
            prev = g
            time.sleep(.04)

    def _motion(self, track, now):
        if len(track) < 4:
            return
        xs = [p[1] for p in track]
        dx = xs[-1] - xs[0]
        turns = sum(1 for i in range(1, len(xs) - 1) if (xs[i] - xs[i - 1]) * (xs[i + 1] - xs[i]) < 0 and abs(xs[i] - xs[i - 1]) > .02)
        if turns >= 3 and max(xs) - min(xs) > .12:
            self._fire("wave")
            track.clear()
        elif abs(dx) > .35 and track[-1][0] - track[0][0] < .6:
            self._fire("swipe_right" if dx > 0 else "swipe_left")
            track.clear()
