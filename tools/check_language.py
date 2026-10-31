"""Find any Hungarian left in the final clips.

    python3 tools/check_language.py media/full deliverables/full

Two independent checks per clip:
1. Original audio passing through: windows where the final audio matches the Hungarian original
   (waveform correlation), e.g. restored name shouts / screams, or audio the dub left untouched.
2. Language of every spoken phrase in the final audio (Whisper language ID, padded phrase audio),
   plus an English and a Hungarian transcript of any phrase that is not clearly English.
Writes deliverables/full/language_check.json.
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel

SR = 16000


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def phrases(x, hop=160):
    n = len(x) // hop
    db = np.array([20 * np.log10(np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(n)])
    on = db > max(-50, db.max() - 30)
    segs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            segs.append([s, i]); s = None
    if s is not None:
        segs.append([s, n])
    out = []
    for a, b in segs:
        if out and (a - out[-1][1]) * hop / SR < 0.25:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a * hop / SR, b * hop / SR) for a, b in out if (b - a) * hop / SR >= 0.12]


def passthrough(fin, hu, win=0.25):
    """Windows where the final audio is the original Hungarian audio."""
    w = int(win * SR)
    hits = []
    for i in range(0, min(len(fin), len(hu)) - w, w // 2):
        a, b = fin[i:i + w], hu[i:i + w]
        ea = np.sqrt(np.mean(a ** 2))
        if 20 * np.log10(ea + 1e-9) < -45:
            continue
        c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        if c > 0.8:
            hits.append(round(i / SR, 2))
    spans = []
    for t in hits:
        if spans and t - spans[-1][1] <= win:
            spans[-1][1] = t + win
        else:
            spans.append([t, t + win])
    return [[round(a, 2), round(b, 2)] for a, b in spans]


def main():
    media, finals = sys.argv[1:3]
    model = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    report = []
    for f in sorted(glob.glob(os.path.join(finals, "*_EN.mp4"))):
        clip = f.split("Splits")[1][:8]
        fin = load(f)
        hu = load(glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0])
        r = {"clip": clip, "original_audio": passthrough(fin, hu), "phrases": []}
        for a, b in phrases(fin):
            seg = fin[int(max(0, a - 0.1) * SR):int((b + 0.1) * SR)]
            pad = np.concatenate([np.zeros(SR // 2, np.float32), seg, np.zeros(SR // 2, np.float32)])
            lang, prob, allp = model.detect_language(pad)
            probs = dict(allp)
            p = {"t": [round(a, 2), round(b, 2)], "lang": lang, "en": round(probs.get("en", 0), 2),
                 "hu": round(probs.get("hu", 0), 2)}
            if lang != "en" or p["en"] < 0.7:
                s_en, _ = model.transcribe(pad, language="en", beam_size=5, condition_on_previous_text=False)
                s_hu, _ = model.transcribe(pad, language="hu", beam_size=5, condition_on_previous_text=False)
                p["as_en"] = " ".join(s.text.strip() for s in s_en)
                p["as_hu"] = " ".join(s.text.strip() for s in s_hu)
            r["phrases"].append(p)
        flagged = [p for p in r["phrases"] if p["lang"] != "en" or p["en"] < 0.7]
        print(clip, "original-audio:", r["original_audio"] or "-", "| phrases:", len(r["phrases"]),
              "| not clearly English:", json.dumps(flagged, ensure_ascii=False) if flagged else "-", flush=True)
        report.append(r)
    json.dump(report, open(os.path.join(finals, "language_check.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
