"""Which language is actually spoken? Compare how well English, Serbo-Croatian and Hungarian
transcripts fit each speech segment (Whisper avg log-prob with the language forced), for the
original clips and the final English clips. Forcing English on Serbian audio makes Whisper translate
silently, so a plain English transcript is not proof; the log-prob comparison is.

    python3 tools/check_language2.py media/full deliverables/full [clip ...]
Writes deliverables/full/language_check2.json.
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
        if out and (a - out[-1][1]) * hop / SR < 0.3:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a * hop / SR, b * hop / SR) for a, b in out if (b - a) * hop / SR >= 0.35]


def fit(model, x):
    """Per language: transcript and duration-weighted mean avg_logprob."""
    out = {}
    for lang in LANGS:
        segs, _ = model.transcribe(x, language=lang, beam_size=5, condition_on_previous_text=False,
                                   without_timestamps=False)
        segs = list(segs)
        w = sum(max(0.1, s.end - s.start) for s in segs) or 1
        lp = sum(s.avg_logprob * max(0.1, s.end - s.start) for s in segs) / w if segs else -9
        out[lang] = {"lp": round(lp, 3), "text": " / ".join(s.text.strip() for s in segs)}
    return out


def main():
    media, finals = sys.argv[1:3]
    only = set(sys.argv[3:])
    model = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    res = []
    for f in sorted(glob.glob(os.path.join(finals, "*_EN.mp4"))):
        clip = f.split("Splits")[1][:8]
        if only and clip not in only:
            continue
        r = {"clip": clip}
        x = load(glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0])
        o = {"fit": fit(model, x)}
        o["best"] = max(LANGS, key=lambda L: o["fit"][L]["lp"])
        r["orig"] = o
        y = load(f)
        r["final"] = []
        for a, b in phrases(y):
            seg = y[int(max(0, a - 0.15) * SR):int((b + 0.15) * SR)]
            seg = np.concatenate([np.zeros(SR // 4, np.float32), seg, np.zeros(SR // 4, np.float32)])
            ph = {"t": [round(a, 2), round(b, 2)], "fit": fit(model, seg)}
            ph["best"] = max(LANGS, key=lambda L: ph["fit"][L]["lp"])
            r["final"].append(ph)
        res.append(r)
        bad = [p for p in r["final"] if p["best"] != "en"]
        print(f"{clip} ORIG={o['best']} [{o['fit'][o['best']]['text'][:90]}] | final phrases {len(r['final'])}, "
              f"not English: " + ("; ".join(f"{p['t']} {p['best']} (lp en {p['fit']['en']['lp']} vs {p['fit'][p['best']]['lp']}) "
                                           f"'{p['fit'][p['best']]['text'][:70]}' / en: '{p['fit']['en']['text'][:70]}'" for p in bad) or "-"),
              flush=True)
        json.dump(res, open(os.path.join(finals, "language_check2.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
