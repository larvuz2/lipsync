"""Local side of re-voicing wrong auto-dub lines (no API key needed).

    python3 tools/fixes_local.py voices exchange/full   # build fix_inputs/voice_<char>.wav from the dub itself
    python3 tools/fixes_local.py apply  exchange/full   # pick best TTS take, fit timing, splice into en/<clip>_EN.wav

fixes.json:
  "characters": {"<char>": [[clip, t0, t1], ...]}   English dub segments of that character (clone sample)
  "lines": [{"id", "clip", "start", "end", "character", "en", "tts"}]
     start/end = span of the wrong English in the clip's dub track (seconds), which gets replaced.
The original dub tracks are kept in en_orig/ the first time a clip is touched.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

SR = 48000


def load(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def save(path, x, stereo=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = np.stack([x, x], 1) if stereo else x[:, None]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(data.shape[1]), "-i", "-",
                    "-c:a", "pcm_s24le", path], input=data.astype(np.float32).tobytes(), check=True)


def fdb(x, hop=480):
    n = max(1, len(x) // hop)
    return np.array([20 * np.log10(np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(n)])


def trim(x, rel=40):
    db = fdb(x)
    on = np.where(db > db.max() - rel)[0]
    return x[max(0, on[0] * 480 - 960):min(len(x), (on[-1] + 1) * 480 + 960)]


def stretch(x, n):
    tempo = len(x) / n
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        save(a, x, stereo=False)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a, "-af",
                        f"rubberband=tempo={tempo:.6f}:window=short:formant=preserved:pitchq=quality:transients=mixed",
                        "-c:a", "pcm_f32le", b], check=True)
        y = load(b)
    return np.pad(y[:n], (0, max(0, n - len(y))))


def norm(t):
    t = t.lower().replace("ó", "o").replace("á", "a").replace("é", "e")
    return re.sub(r"[^a-z ]", " ", t).split()


def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        prev, d[0] = d.copy(), i
        for j in range(1, len(h) + 1):
            d[j] = min(prev[j] + 1, d[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(h)] / max(1, len(r))


def en_path(ex, clip, orig=False):
    return os.path.join(ex, "en_orig" if orig else "en", f"{clip}_EN.wav")


def voices(ex):
    cfg = json.load(open(os.path.join(ex, "fixes.json")))
    for char, segs in cfg["characters"].items():
        parts = []
        for clip, a, b in segs:
            src = en_path(ex, clip, orig=os.path.exists(en_path(ex, clip, orig=True)))
            x = load(src)[int(a * SR):int(b * SR)]
            parts += [x, np.zeros(int(0.3 * SR), np.float32)]
        s = np.concatenate(parts)
        s *= 10 ** (-3 / 20) / (np.abs(s).max() + 1e-9)
        save(os.path.join(ex, "fix_inputs", f"voice_{char}.wav"), s, stereo=False)
        print(f"voice {char}: {len(s) / SR:.1f} s from {len(segs)} segments")


def apply(ex):
    from faster_whisper import WhisperModel
    asr = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    cfg = json.load(open(os.path.join(ex, "fixes.json")))
    man = json.load(open(os.path.join(ex, "fix_tts", "manifest.json")))
    report = []
    work = {}  # clip -> track being rebuilt from the original dub (reruns never stack edits)
    media = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ex))), "media", "full")
    for ln in sorted(cfg["lines"] + cfg.get("edits", []), key=lambda l: (l["clip"], l["start"])):
        clip = ln["clip"]
        if not os.path.exists(en_path(ex, clip, orig=True)):
            os.makedirs(os.path.join(ex, "en_orig"), exist_ok=True)
            shutil.copy(en_path(ex, clip), en_path(ex, clip, orig=True))
        orig = load(en_path(ex, clip, orig=True))
        cur = work.setdefault(clip, orig.copy())
        a, b = int(ln["start"] * SR), int(min(ln["end"], len(orig) / SR) * SR)
        kind = ln.get("type", "tts")
        if kind in ("mute", "restore"):
            m = int(0.02 * SR)
            lo, hi = max(0, a - m), min(len(cur), b + m)
            ramp = np.ones(hi - lo)
            ramp[:a - lo] = np.linspace(1, 0, a - lo); ramp[a - lo:b - lo] = 0; ramp[b - lo:] = np.linspace(0, 1, hi - b)
            cur[lo:hi] *= ramp
            if kind == "restore":  # the original actor's own audio (names, screams): same timeline
                hu = load(glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0])
                seg = hu[lo:hi] * (1 - ramp)
                cur[lo:lo + len(seg)] += seg
            report.append({"id": ln["id"], "clip": clip, "type": kind, "span": [ln["start"], ln["end"]]})
            print(json.dumps(report[-1]), flush=True)
            continue
        span = (b - a) / SR
        # room after the span: up to the next English speech in the original dub (or clip end)
        db = fdb(orig)
        on = db > max(-52, db.max() - 32)
        k = b // 480
        while k < len(on) and not on[k]:
            k += 1
        room = (min(k * 480, len(orig)) - a) / SR - 0.08
        cands = []
        for t in [t for t in man["takes"] if t["id"] == ln["id"]]:
            x = trim(load(os.path.join(ex, t["file"])))
            x16 = load(os.path.join(ex, t["file"]), 16000)
            segs, _ = asr.transcribe(x16, language="en", beam_size=5)
            heard = " ".join(s.text.strip() for s in segs)
            cands.append({**t, "x": x, "nat": len(x) / SR, "heard": heard, "wer": wer(ln["en"], heard)})
        good = [c for c in cands if c["wer"] <= 0.25] or cands
        best = min(good, key=lambda c: abs(np.log(span / c["nat"])))
        dur = min(max(span, best["nat"] * 0.87), best["nat"] * 1.12, max(room, span))
        n = int(dur * SR)
        y = stretch(best["x"], n)
        ref = orig[a:b]
        if np.percentile(fdb(ref), 90) < -55:  # inserting where the dub is silent: match the Hungarian level
            ref = load(glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0])[a:b]
        y *= 10 ** ((np.percentile(fdb(ref), 90) - np.percentile(fdb(y), 90)) / 20)
        fade = int(0.01 * SR)
        y[:fade] *= np.linspace(0, 1, fade); y[-fade:] *= np.linspace(1, 0, fade)
        m = int(0.02 * SR)
        lo, hi = max(0, a - m), min(len(cur), max(b, a + n) + m)
        ramp = np.ones(hi - lo)
        ramp[:a - lo] = np.linspace(1, 0, a - lo)
        ramp[a - lo:max(b, a + n) - lo] = 0
        ramp[max(b, a + n) - lo:] = np.linspace(0, 1, hi - max(b, a + n))
        cur[lo:hi] *= ramp
        cur[a:a + n] += y[:len(cur) - a]
        r = {"id": ln["id"], "clip": clip, "en": ln["en"], "take": best["file"], "heard": best["heard"],
             "wer": round(best["wer"], 2), "span_s": round(span, 2), "natural_s": round(best["nat"], 2),
             "placed_s": round(dur, 2)}
        report.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    for clip, cur in work.items():
        save(en_path(ex, clip), cur)
    json.dump(report, open(os.path.join(ex, "fix_tts", "applied.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    {"voices": voices, "apply": apply}[sys.argv[1]](sys.argv[2])
