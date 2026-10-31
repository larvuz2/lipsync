"""Targeted language check (fast version of check_language2).

    python3 tools/check_language3.py media/full deliverables/full

1. Language ID of every original clip (is the original Hungarian or Serbian?).
2. For every final phrase that check_language.py did not find clearly English (en < 0.7), compare how
   well English, Serbo-Croatian and Hungarian transcripts fit (avg log-prob with the language forced).
Writes deliverables/full/language_check3.json.
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel

SR = 16000
LANGS = ("en", "hr", "hu")


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def fit(model, x):
    out = {}
    for lang in LANGS:
        segs = list(model.transcribe(x, language=lang, beam_size=5, condition_on_previous_text=False)[0])
        w = sum(max(0.1, s.end - s.start) for s in segs) or 1
        lp = sum(s.avg_logprob * max(0.1, s.end - s.start) for s in segs) / w if segs else -9
        out[lang] = {"lp": round(lp, 3), "text": " / ".join(s.text.strip() for s in segs)}
    return out


def main():
    media, finals = sys.argv[1:3]
    model = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    first = {r["clip"]: r for r in json.load(open(os.path.join(finals, "language_check.json")))}
    res = {}
    for f in sorted(glob.glob(os.path.join(finals, "*_EN.mp4"))):
        clip = f.split("Splits")[1][:8]
        x = load(glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0])
        _, _, allp = model.detect_language(x)
        d = dict(allp)
        slav = d.get("hr", 0) + d.get("sr", 0) + d.get("bs", 0)
        r = {"orig_lid": {"hu": round(d.get("hu", 0), 2), "slavic": round(slav, 2), "en": round(d.get("en", 0), 2)},
             "orig_lang": "serbian" if slav > d.get("hu", 0) else "hungarian", "phrases": []}
        y = None
        for p in first[clip]["phrases"]:
            if p["lang"] == "en" and p["en"] >= 0.7:
                continue
            if p["t"][1] - p["t"][0] < 0.35:
                continue
            y = load(f) if y is None else y
            a, b = p["t"]
            seg = y[int(max(0, a - 0.15) * SR):int((b + 0.15) * SR)]
            seg = np.concatenate([np.zeros(SR // 4, np.float32), seg, np.zeros(SR // 4, np.float32)])
            ph = {"t": p["t"], "fit": fit(model, seg)}
            ph["best"] = max(LANGS, key=lambda L: ph["fit"][L]["lp"])
            r["phrases"].append(ph)
        res[clip] = r
        bad = [p for p in r["phrases"] if p["best"] != "en"]
        print(f"{clip} orig={r['orig_lang']} {r['orig_lid']} | checked {len(r['phrases'])}, best not English: " +
              ("; ".join(f"{p['t']} {p['best']} (en {p['fit']['en']['lp']} vs {p['fit'][p['best']]['lp']}) "
                         f"'{p['fit'][p['best']]['text'][:60]}' | en: '{p['fit']['en']['text'][:60]}'" for p in bad) or "-"),
              flush=True)
        json.dump(res, open(os.path.join(finals, "language_check3.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
