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


def squeeze_pauses(x, rel=35, keep=0.08, min_gap=0.15):
    """Shorten silent gaps inside a take (TTS adds sentence pauses the dub doesn't have)."""
    db = fdb(x)
    on = db > db.max() - rel
    out, k, n = [], 0, len(on)
    while k < n:
        j = k
        while j < n and on[j] == on[k]:
            j += 1
        seg = x[k * 480:j * 480]
        if not on[k] and k > 0 and j < n and (j - k) * 480 / SR > min_gap:
            h = int(keep * SR / 2)
            seg = np.concatenate([seg[:h], seg[-h:]])
        out.append(seg)
        k = j
    return np.concatenate(out + [x[n * 480:]])


def boundary(x, t, search=0.08):
    """Move a cut point to the quietest 10 ms frame within +-search seconds."""
    lo, hi = max(0, int((t - search) * SR)), min(len(x), int((t + search) * SR))
    best, bt = 1e9, t
    for i in range(lo, max(lo + 1, hi - 480), 240):
        e = float(np.mean(x[i:i + 480] ** 2))
        if e < best:
            best, bt = e, (i + 240) / SR
    return bt


def similar(a, b):
    import difflib
    return difflib.SequenceMatcher(None, "".join(norm(a)), "".join(norm(b))).ratio()


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


def snap_out(x, a, b, limit=0.35, rel=35):
    """Widen [a, b] (samples) to the nearest pause on each side (within limit s), so no tail of an old
    dub word survives next to a replaced span (Whisper's word times end early)."""
    db = fdb(x)
    quiet = db < max(-50, db.max() - rel)
    k, lim = b // 480, int(limit * 100)
    j = k
    while j < min(len(quiet), k + lim) and not (quiet[j:j + 5].all()):
        j += 1
    b2 = j * 480 if j < min(len(quiet), k + lim) else b
    k = a // 480
    j = k
    while j > max(0, k - lim) and not (quiet[max(0, j - 5):j].all()):
        j -= 1
    a2 = j * 480 if j > max(0, k - lim) else a
    return max(0, min(a, a2)), min(len(x), max(b, b2))


def clear(cur, a, b, f=0.015):
    """Fade out cur over [a, b] (samples) with short ramps."""
    f = int(f * SR)
    lo, hi = max(0, a - f), min(len(cur), b + f)
    ramp = np.ones(hi - lo)
    ramp[:a - lo] = np.linspace(1, 0, a - lo)
    ramp[a - lo:b - lo] = 0
    ramp[b - lo:] = np.linspace(0, 1, hi - b)
    cur[lo:hi] *= ramp


def add(cur, y, at, f=0.01):
    y = y.copy()
    f = int(f * SR)
    y[:f] *= np.linspace(0, 1, f); y[-f:] *= np.linspace(1, 0, f)
    at = max(0, at)
    n = min(len(y), len(cur) - at)
    cur[at:at + n] += y[:n]


def quietest(x, t, search):
    return boundary(x, t, search)


def edges(x, words, i, j, rel=40):
    """Cut points (s) for aligned words [i, j). CTC alignment marks the core of each word, not its
    edges, so cut at the quietest point of the gap to the neighbouring word, or at the speech
    onset/offset when there is no neighbour."""
    db = fdb(x)
    thr = db.max() - rel
    if i > 0:
        g0, g1 = words[i - 1][2], words[i][1]
        c0 = quietest(x, (g0 + g1) / 2, max(0.015, (g1 - g0) / 2))
    else:
        k = int(words[i][1] * 100)
        while k > 0 and k > int((words[i][1] - 0.4) * 100) and db[k - 1] > thr:
            k -= 1
        c0 = max(0.0, k / 100 - 0.01)
    if j < len(words):
        g0, g1 = words[j - 1][2], words[j][1]
        c1 = quietest(x, (g0 + g1) / 2, max(0.015, (g1 - g0) / 2))
    else:
        k = int(words[j - 1][2] * 100)
        while k < len(db) - 1 and k < int((words[j - 1][2] + 0.4) * 100) and db[k + 1] > thr:
            k += 1
        c1 = min(len(x) / SR, k / 100 + 0.02)
    return c0, c1


def splice_word(ex, ln, man, tr, orig, cur, align, hear):
    """Replace wrong word(s) (usually a name) inside the dub's own line with the same word(s) cut from a
    TTS take of the corrected line, in the cloned dub voice. Word boundaries come from forced alignment
    of the known text, on both the dub and the take. If the new word is longer, the rest of the dub line
    is pushed later into its next pause, so nothing is squeezed."""
    from align import find
    # the dub sentence(s) around the wrong word, aligned
    segs = [s for s in tr[ln["clip"]]["en"] if s["end"] > ln["start"] - 0.2 and s["start"] < ln["end"] + 0.2]
    r0 = max(0.0, segs[0]["start"] - 0.3)
    r1 = min(len(orig) / SR, segs[-1]["end"] + 0.6)
    dw = align(orig[int(r0 * SR):int(r1 * SR)], SR, " ".join(s["text"] for s in segs))
    dw = [(w, s + r0, e + r0) for w, s, e in dw]
    i, j, dsc = find(dw, ln["was"])
    d0, d1 = edges(orig, dw, i, j)
    # the corrected word(s) in each take, aligned against the take's own script
    best = None
    for t in [t for t in man["takes"] if t["id"] == ln["take_line"]]:
        x = load(os.path.join(ex, t["file"]))
        tw = align(x, SR, ln["tts"])
        ti, tj, tsc = find(tw, ln["word"])
        c0, c1 = edges(x, tw, ti, tj)
        seg = x[int(c0 * SR):int(c1 * SR)]
        cand = {"take": t["file"], "seg": seg, "score": tsc, "ratio": len(seg) / SR / (d1 - d0),
                "heard": hear(t["file"])}
        # prefer a take that is heard exactly as scripted, then the length closest to the slot
        key = (wer(ln["tts"], cand["heard"]) > 0, -round(tsc, 1), abs(np.log(cand["ratio"])))
        if best is None or key < best[0]:
            best = (key, cand)
    c = best[1]
    seg = c["seg"]
    n = int((d1 - d0) * SR)
    L = len(seg)
    if L > n * 1.05 and i == 0:
        # first word of the line with silence before it: start a little earlier instead of speeding up
        db = fdb(orig)
        k, lim = int(d0 * 100), int((d0 - 0.15) * 100)
        while k > max(0, lim) and db[k - 1] < db.max() - 40:
            k -= 1
        d0 -= min((L - n) / SR, max(0.0, d0 - k / 100 - 0.02))
        n = int((d1 - d0) * SR)
    push = 0
    if L > n * 1.12:
        # make room: move the rest of the line later, into the first pause after the slot that is long enough
        need = int(L / 1.12) - n
        gaps = [(dw[k][2], dw[k + 1][1]) for k in range(j - 1, len(dw) - 1)]
        tail_end = dw[-1][2]
        db = fdb(cur)
        on = db > max(-52, db.max() - 32)
        q = int(tail_end * SR) // 480 + 4
        while q < len(on) and not on[q]:
            q += 1
        gaps.append((tail_end, q * 480 / SR))
        if gaps[0][1] - d1 >= need / SR + 0.04:
            push = need  # the pause right after the word is long enough: just use it
        else:
            for g0, g1 in gaps[1:]:
                if g1 - g0 >= need / SR + 0.05:
                    g0s = int(quietest(orig, g0 + 0.02, 0.03) * SR)
                    d1s = int(d1 * SR)
                    moved = cur[d1s:g0s].copy()
                    clear(cur, d1s, g0s, f=0.008)
                    add(cur, moved, d1s + need, f=0.008)
                    push = need
                    break
    n2 = n + push
    m = int(np.clip(L, n2 / 1.12, n2 * 1.25))
    m = min(m, n2)
    y = stretch(seg, m)
    ref = orig[int(d0 * SR):int(d1 * SR)]
    y *= 10 ** ((np.percentile(fdb(ref), 90) - np.percentile(fdb(y), 90)) / 20)
    clear(cur, int(d0 * SR), int(d0 * SR) + n2, f=0.008)
    add(cur, y, int(d0 * SR) + (n2 - m) // 2, f=0.008)
    return {"id": ln["id"], "clip": ln["clip"], "type": "word", "was": ln["was"], "word": ln["word"],
            "take": c["take"], "take_heard": c["heard"], "align_match": round(min(dsc, c["score"]), 2),
            "slot_s": [round(d0, 2), round(d1, 2)], "word_s": round(L / SR, 2), "pushed_s": round(push / SR, 2),
            "speed": round(L / m, 2)}


def apply(ex, only=()):
    from faster_whisper import WhisperModel
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from align import align
    cfg = json.load(open(os.path.join(ex, "fixes.json")))
    man = json.load(open(os.path.join(ex, "fix_tts", "manifest.json")))
    tr = json.load(open(os.path.join(ex, "transcripts.json")))  # transcripts of the original dub
    heard_p = os.path.join(ex, "fix_tts", "heard.json")
    heard = json.load(open(heard_p)) if os.path.exists(heard_p) else {}
    asr = None
    media = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ex))), "media", "full")
    items = sorted(cfg["lines"] + cfg.get("edits", []), key=lambda l: (l["clip"], l["start"]))
    report = []
    for clip in sorted({l["clip"] for l in items}):
        if only and clip not in only:
            continue
        if not os.path.exists(en_path(ex, clip, orig=True)):
            os.makedirs(os.path.join(ex, "en_orig"), exist_ok=True)
            shutil.copy(en_path(ex, clip), en_path(ex, clip, orig=True))
        orig = load(en_path(ex, clip, orig=True))  # rebuilt from the original dub every run
        hu = load(glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0])
        cur = orig.copy()
        mine = [l for l in items if l["clip"] == clip]
        span_of = {}
        # 1) clear the old dub under every replaced / muted / restored span, out to the next pause
        for ln in mine:
            kind = ln.get("type", "tts")
            a, b = int(ln["start"] * SR), int(min(ln["end"], len(orig) / SR) * SR)
            if kind == "word":
                continue
            a2, b2 = snap_out(orig, a, b) if not ln.get("exact") else (a, b)
            clear(cur, a2, b2)
            span_of[ln["id"]] = (a2, b2)
            if kind == "restore":  # the original actor's own audio (names, screams), same timeline
                f = int(0.02 * SR)
                add(cur, hu[max(0, a - f):b + f], max(0, a - f), f=0.02)
            if kind in ("mute", "restore"):
                report.append({"id": ln["id"], "clip": clip, "type": kind, "span": [ln["start"], ln["end"]],
                               "cleared": [round(a2 / SR, 2), round(b2 / SR, 2)]})
        # 2) single-word swaps inside kept dub lines
        def hear(f):
            nonlocal asr
            if f not in heard:
                if asr is None:
                    asr = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
                segs, _ = asr.transcribe(load(os.path.join(ex, f), 16000), language="en", beam_size=5)
                heard[f] = " ".join(s.text.strip() for s in segs)
            return heard[f]
        for ln in mine:
            if ln.get("type") == "word":
                report.append(splice_word(ex, ln, man, tr, orig, cur, align, hear))
        # 3) new lines
        dub_ref = np.percentile(fdb(orig), 90)
        hu_ref = np.percentile(fdb(hu), 90)
        for ln in mine:
            if ln.get("type", "tts") != "tts":
                continue
            a, b = int(ln["start"] * SR), int(min(ln["end"], len(orig) / SR) * SR)
            span = (b - a) / SR
            db = fdb(cur)
            on = db > max(-52, db.max() - 32)
            for o in mine:  # where the other new lines will go
                if o is not ln and o.get("type", "tts") == "tts":
                    on[int(o["start"] * SR) // 480:int(o["end"] * SR) // 480 + 1] = True
            on[a // 480:b // 480 + 1] = False
            k = b // 480
            while k < len(on) and not on[k]:
                k += 1
            room = (min(k * 480, len(orig)) - a) / SR - 0.08
            k = a // 480 - 1
            while k >= 0 and not on[k] and (a - k * 480) / SR < ln.get("lead", 0.2):
                k -= 1
            lead = max(0.0, (a - (k + 1) * 480) / SR - 0.06)
            cands = []
            for t in [t for t in man["takes"] if t["id"] == ln["id"]]:
                x = trim(load(os.path.join(ex, t["file"])))
                if len(x) / SR > span * 1.05:  # too long: drop the sentence pauses TTS adds
                    x = squeeze_pauses(x)
                if t["file"] not in heard:
                    if asr is None:
                        asr = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
                    segs, _ = asr.transcribe(load(os.path.join(ex, t["file"]), 16000), language="en", beam_size=5)
                    heard[t["file"]] = " ".join(s.text.strip() for s in segs)
                h = heard[t["file"]]
                cands.append({**t, "x": x, "nat": len(x) / SR, "heard": h, "wer": wer(ln.get("tts", ln["en"]), h)})
            good = [c for c in cands if c["wer"] <= 0.25] or cands
            avail = max(room, span) + lead
            best = min(good, key=lambda c: (c["nat"] / 1.2 > avail, abs(np.log(span / c["nat"]))))
            nat = best["nat"]
            # natural pace where possible: speed up at most 1.12x to meet the span, 1.2x if room is short,
            # slow down at most 1.08x to fill it
            dur = min(max(span, nat / 1.12), nat * 1.08)
            too_long = False
            if dur > avail:
                dur = max(avail, nat / 1.2)
                too_long = dur > avail + 1e-3
                dur = min(dur, avail)
            shift = max(0.0, dur - max(room, span))
            a0 = a - int(shift * SR)
            n = int(dur * SR)
            y = stretch(best["x"], n)
            # loudness: as loud as the Hungarian line is within its own clip (the dub is matched per clip)
            target = np.percentile(fdb(hu[a:b]), 90) - hu_ref + dub_ref
            y *= 10 ** ((target - np.percentile(fdb(y), 90)) / 20)
            clear(cur, a0, a0 + n)
            add(cur, y, a0)
            r = {"id": ln["id"], "clip": clip, "en": ln["en"], "take": best["file"], "heard": best["heard"],
                 "wer": round(best["wer"], 2), "span_s": round(span, 2), "natural_s": round(nat, 2),
                 "placed": [round(a0 / SR, 2), round((a0 + n) / SR, 2)], "speed": round(nat / dur, 2)}
            if too_long:
                r["TOO_LONG"] = True
            report.append(r)
        save(en_path(ex, clip), cur)
        for r in report:
            if r["clip"] == clip:
                print(json.dumps(r, ensure_ascii=False), flush=True)
    json.dump(heard, open(heard_p, "w"), indent=1, ensure_ascii=False)
    ap = os.path.join(ex, "fix_tts", "applied.json")
    if only and os.path.exists(ap):  # partial run: keep the report of the other clips
        report = [r for r in json.load(open(ap)) if r["clip"] not in only] + report
    json.dump(report, open(ap, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    if sys.argv[1] == "apply":
        apply(sys.argv[2], set(sys.argv[3:]))
    else:
        voices(sys.argv[2])
