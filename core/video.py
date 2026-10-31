"""YouTube Studio: auto-cut silences, auto-captions, Shorts/TikToks from the best moments, and titles/
descriptions/chapters. Uses ffmpeg (installed by 1_SETUP.bat) + Groq Whisper for timestamps.

Everything renders on the CPU (your GT 710 can't hardware-encode), so a 10-minute 1080p video takes
roughly 10-20 minutes. STOP cancels a render.
"""
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time

from .tools import CTX, tool

IS_WIN = platform.system() == "Windows"
FLAGS = 0x08000000 if IS_WIN else 0
VIDEO_EXT = (".mp4", ".mkv", ".mov", ".webm", ".avi", ".flv")


def ffmpeg(name="ffmpeg"):
    p = shutil.which(name)
    if p:
        return p
    if IS_WIN:
        pats = [rf"%LOCALAPPDATA%\Microsoft\WinGet\Links\{name}.exe",
                rf"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\{name}.exe",
                rf"C:\ffmpeg\bin\{name}.exe", rf"%ProgramFiles%\ffmpeg\bin\{name}.exe"]
        for pat in pats:
            hits = glob.glob(os.path.expandvars(pat))
            if hits:
                return hits[0]
    raise RuntimeError("ffmpeg isn't installed — run 1_SETUP.bat again (it installs ffmpeg).")


def _find_video(path):
    from .tools import _expand
    p = _expand(path)
    if os.path.isfile(p):
        return p
    # allow "my latest video" style: newest video in Videos / Downloads / Desktop
    if path.lower() in ("latest", "newest", "last", "my latest video", ""):
        cands = []
        for d in ("Videos", "Downloads", "Desktop"):
            for ext in VIDEO_EXT:
                cands += glob.glob(os.path.join(os.path.expanduser("~"), d, "**", "*" + ext), recursive=True)
        if cands:
            return max(cands, key=os.path.getmtime)
    raise FileNotFoundError(f"No video at '{path}'.")


def _run(args, label="Rendering", total=None, cwd=None):
    """Runs ffmpeg with progress updates; STOP kills it."""
    emit = CTX.get("emit", lambda *a, **k: None)
    cancel = CTX.get("cancel")
    proc = subprocess.Popen([ffmpeg()] + ["-hide_banner", "-y"] + args, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", creationflags=FLAGS, cwd=cwd)
    tail, last = [], 0
    for line in proc.stderr:
        tail = (tail + [line])[-25:]
        if cancel and cancel.is_set():
            proc.kill()
            raise RuntimeError("Render cancelled.")
        m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
        if m and total and time.time() - last > 1.5:
            sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            emit("status", text=f"{label} {min(99, int(sec / total * 100))}%")
            last = time.time()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + "".join(tail)[-800:])


def duration(path):
    r = subprocess.run([ffmpeg("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                       capture_output=True, text=True, creationflags=FLAGS)
    return float(json.loads(r.stdout)["format"]["duration"])


def _out(path, suffix, ext=".mp4"):
    base, _ = os.path.splitext(path)
    return f"{base}_{suffix}{ext}"


ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]


# ------------------------------------------------------------------ transcription
def transcribe(path):
    brain = CTX.get("brain")
    prov = brain.groq_like if brain else None
    if not prov:
        raise RuntimeError("Captions need a Groq key (free) for Whisper.")
    import requests
    tmp = tempfile.mkdtemp(prefix="orion_tx_")
    total = duration(path)
    chunk = 600
    segments, words = [], []
    try:
        for i, start in enumerate(range(0, int(total) + 1, chunk)):
            mp3 = os.path.join(tmp, f"a{i}.mp3")
            _run(["-ss", str(start), "-t", str(chunk), "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", mp3])
            with open(mp3, "rb") as f:
                data = f.read()
            if len(data) < 2000:
                continue
            CTX.get("emit", lambda *a, **k: None)("status", text=f"Transcribing {min(100, int(start / max(total, 1) * 100))}%")
            r = requests.post(f"{prov.base_url}/audio/transcriptions",
                              headers={"Authorization": f"Bearer {prov.api_key}"},
                              files={"file": ("a.mp3", data, "audio/mpeg")},
                              data=[("model", prov.stt or "whisper-large-v3-turbo"), ("response_format", "verbose_json"),
                                    ("timestamp_granularities[]", "segment"), ("timestamp_granularities[]", "word")],
                              timeout=300)
            if r.status_code != 200:
                raise RuntimeError(f"Whisper failed: HTTP {r.status_code} {r.text[:200]}")
            j = r.json()
            for s in j.get("segments", []):
                segments.append({"start": s["start"] + start, "end": s["end"] + start, "text": s["text"].strip()})
            for w in j.get("words", []) or []:
                words.append({"start": w["start"] + start, "end": w["end"] + start, "word": w["word"].strip()})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return segments, words


def _ts(t):
    h, rem = divmod(max(0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s - int(s)) * 1000):03}"


def make_srt(segments, words, offset=0.0, max_words=4, upper=True):
    """Short punchy caption chunks (Shorts style) when word timings exist, else whole segments."""
    cues = []
    if words:
        chunk = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= max_words or re.search(r"[.!?,]$", w["word"]):
                cues.append((chunk[0]["start"], chunk[-1]["end"], " ".join(x["word"] for x in chunk)))
                chunk = []
        if chunk:
            cues.append((chunk[0]["start"], chunk[-1]["end"], " ".join(x["word"] for x in chunk)))
    else:
        cues = [(s["start"], s["end"], s["text"]) for s in segments]
    out = []
    for i, (a, b, t) in enumerate(cues, 1):
        a, b = a - offset, b - offset
        if b <= 0:
            continue
        out.append(f"{i}\n{_ts(a)} --> {_ts(max(b, a + 0.3))}\n{t.upper() if upper else t}\n")
    return "\n".join(out)


STYLE = ("FontName=Arial Black,FontSize={size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
         "BackColour=&H64000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV={mv}")


def _burn(src, srt_text, dst, vf_prefix="", size=16, mv=40, total=None):
    tmp = tempfile.mkdtemp(prefix="orion_sub_")
    try:
        with open(os.path.join(tmp, "subs.srt"), "w", encoding="utf-8") as f:
            f.write(srt_text)
        vf = (vf_prefix + "," if vf_prefix else "") + f"subtitles=subs.srt:force_style='{STYLE.format(size=size, mv=mv)}'"
        _run(["-i", os.path.abspath(src), "-vf", vf] + ENC + [os.path.abspath(dst)], "Burning captions", total, cwd=tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ tools
@tool("Get a video's length, resolution and size. Path can be 'latest' for the newest video in Videos/Downloads/Desktop.",
      {"path": ("string", "Video file path or 'latest'", True)})
def video_info(path):
    p = _find_video(path)
    r = subprocess.run([ffmpeg("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate", "-of", "json", p], capture_output=True, text=True,
                       creationflags=FLAGS)
    s = json.loads(r.stdout).get("streams", [{}])[0]
    d = duration(p)
    return (f"{os.path.basename(p)}: {int(d // 60)}m{int(d % 60):02}s, {s.get('width')}x{s.get('height')}, "
            f"{os.path.getsize(p) / 2**20:.0f} MB\n{p}")


@tool("Auto-cut a video: removes silences, dead air and long pauses. Saves a new file next to the original.",
      {"path": ("string", "Video file path or 'latest'", True),
       "min_silence": ("number", "Shortest pause to cut, seconds (default 0.7)", False),
       "aggressive": ("boolean", "Cut quieter mumbling too", False)})
def video_autocut(path, min_silence=0.7, aggressive=False):
    p = _find_video(path)
    total = duration(p)
    noise = "-28dB" if aggressive else "-33dB"
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", p, "-af", f"silencedetect=noise={noise}:d={min_silence or 0.7}",
                        "-f", "null", "-"], capture_output=True, text=True, creationflags=FLAGS, encoding="utf-8",
                       errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    pad = 0.15
    keep, cur = [], 0.0
    for s, e in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s - cur > 0.25:
            keep.append((max(0, cur - pad if cur else 0), min(total, s + pad)))
        cur = e
    if total - cur > 0.25:
        keep.append((max(0, cur - pad), total))
    if not starts:
        return "No silences found — nothing to cut."
    removed = total - sum(b - a for a, b in keep)
    parts = []
    for i, (a, b) in enumerate(keep):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}];[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}];")
    graph = "".join(parts) + "".join(f"[v{i}][a{i}]" for i in range(len(keep))) + f"concat=n={len(keep)}:v=1:a=1[v][a]"
    tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write(graph)
    tmp.close()
    out = _out(p, "cut")
    try:
        _run(["-i", p, "-filter_complex_script", tmp.name, "-map", "[v]", "-map", "[a]"] + ENC + [out],
             "Cutting", total - removed)
    finally:
        os.unlink(tmp.name)
    return f"Cut {len(keep) - 1} pauses, removed {removed:.0f}s ({removed / total * 100:.0f}%). Saved: {out}"


@tool("Add auto-captions (subtitles) to a video. burn=true bakes styled captions into the picture; also saves an .srt.",
      {"path": ("string", "Video file path or 'latest'", True), "burn": ("boolean", "Burn into the video (default true)", False),
       "shorts_style": ("boolean", "Big punchy 3-4 word captions (default true)", False)})
def video_captions(path, burn=True, shorts_style=True):
    p = _find_video(path)
    segs, words = transcribe(p)
    if not segs:
        return "No speech found."
    srt = make_srt(segs, words if shorts_style else [], max_words=4 if shorts_style else 12, upper=shorts_style)
    srt_path = _out(p, "captions", ".srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt)
    if burn is False:
        return f"Captions saved: {srt_path}"
    out = _out(p, "captioned")
    _burn(p, srt, out, size=18 if shorts_style else 14, mv=50, total=duration(p))
    return f"Captioned video: {out}\nSubtitles file: {srt_path}"


def _pick_moments(segs, count, length):
    brain = CTX.get("brain")
    lines = "\n".join(f"[{s['start']:.0f}-{s['end']:.0f}] {s['text']}" for s in segs)[:24000]
    ask = (f"Transcript with second timestamps:\n{lines}\n\nPick the {count} most engaging moments for YouTube Shorts "
           f"(funny, hype, clutch plays, strong reactions, good stories). Each about {length}s (between 15 and 59). "
           'Reply with ONLY JSON: [{"start": sec, "end": sec, "title": "short catchy title"}]')
    ans = brain.quick("You are a sharp short-form video editor.", ask, set(), "smart")
    m = re.search(r"\[.*\]", ans, re.S)
    picks = json.loads(m.group(0)) if m else []
    return [x for x in picks if 0 <= float(x["start"]) < float(x["end"])][:count]


@tool("Make vertical Shorts/TikToks from a video's best moments, with big captions. Saves them in a folder.",
      {"path": ("string", "Video file path or 'latest'", True), "count": ("integer", "How many (default 3)", False),
       "length": ("integer", "Target seconds each (default 40, max 59)", False)})
def video_shorts(path, count=3, length=40):
    p = _find_video(path)
    segs, words = transcribe(p)
    if not segs:
        return "No speech found to pick moments from."
    picks = _pick_moments(segs, int(count or 3), min(int(length or 40), 59))
    if not picks:
        return "Couldn't pick moments."
    folder = os.path.splitext(p)[0] + "_shorts"
    os.makedirs(folder, exist_ok=True)
    made = []
    for i, pk in enumerate(picks, 1):
        a, b = float(pk["start"]), min(float(pk["end"]), float(pk["start"]) + 59)
        clip = os.path.join(folder, f"clip{i}.mp4")
        _run(["-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", p] + ENC + [clip], f"Short {i}: cutting", b - a)
        sw = [w for w in words if a <= w["start"] < b]
        ss = [s for s in segs if s["end"] > a and s["start"] < b]
        srt = make_srt(ss, sw, offset=a, max_words=3)
        title = re.sub(r"[^\w\- ]", "", pk.get("title") or f"short {i}")[:40].strip().replace(" ", "_")
        out = os.path.join(folder, f"{i:02}_{title}.mp4")
        _burn(clip, srt, out, "crop=ih*9/16:ih,scale=1080:1920", size=14, mv=120, total=b - a)
        os.remove(clip)
        made.append(f"{os.path.basename(out)} ({b - a:.0f}s) — {pk.get('title')}")
    return f"Made {len(made)} Shorts in {folder}:\n" + "\n".join(made)


@tool("Write a YouTube title, description, tags and chapter timestamps for a video from what's said in it.",
      {"path": ("string", "Video file path or 'latest'", True)})
def video_metadata(path):
    p = _find_video(path)
    segs, _ = transcribe(p)
    lines = "\n".join(f"[{int(s['start'] // 60)}:{int(s['start'] % 60):02}] {s['text']}" for s in segs)[:24000]
    brain = CTX.get("brain")
    out = brain.quick("You are a YouTube growth expert for gaming channels.",
                      f"Transcript:\n{lines}\n\nWrite: 3 title options (clickable, honest, under 70 chars), a description "
                      "(2 short paragraphs + chapters list using the real timestamps), and 15 tags.", set(), "smart")
    md = _out(p, "youtube", ".txt")
    with open(md, "w", encoding="utf-8") as f:
        f.write(out)
    return out + f"\n\n(Saved to {md})"
