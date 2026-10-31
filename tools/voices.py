"""Group every spoken phrase by voice (who is speaking), across all clips.

    python3 tools/voices.py exchange/full/analysis/analysis.json media/full exchange/full/voices.json

Uses the SpeechBrain ECAPA speaker model. Phrases shorter than 0.5 s are embedded but not used to
form groups. Output: per phrase a voice group id, plus group stats (pitch, total speech).
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
import torch

SR = 16000


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def main():
    an_path, media, out = sys.argv[1:4]
    from speechbrain.inference.speaker import EncoderClassifier
    enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                         savedir=os.path.join(os.path.dirname(out), "_ecapa"))
    import librosa
    rows = []
    for rec in json.load(open(an_path)):
        x = load(glob.glob(os.path.join(media, f"*Splits{rec['clip']}.mp4"))[0])
        for k, p in enumerate(rec["phrases"]):
            seg = x[int(p["start"] * SR):int(p["end"] * SR)]
            if len(seg) < int(0.25 * SR):
                continue
            with torch.no_grad():
                e = enc.encode_batch(torch.from_numpy(seg)[None]).squeeze().numpy()
            f0, vf, _ = librosa.pyin(seg, fmin=60, fmax=500, sr=SR, frame_length=2048)
            v = f0[vf]
            rows.append({"clip": rec["clip"], "phrase": k, "start": p["start"], "end": p["end"], "dur": round(p["end"] - p["start"], 2),
                         "f0": round(float(np.median(v)), 1) if len(v) > 3 else None, "emb": e / np.linalg.norm(e)})
    # Agglomerative clustering (average linkage, cosine) on phrases >= 0.5 s, then assign the rest.
    core = [r for r in rows if r["dur"] >= 0.5]
    groups = [[r] for r in core]

    def sim(a, b):
        return float(np.mean([x["emb"] @ y["emb"] for x in a for y in b]))
    while True:
        best, pair = 0.42, None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                s = sim(groups[i], groups[j])
                if s > best:
                    best, pair = s, (i, j)
        if not pair:
            break
        i, j = pair
        groups[i] += groups.pop(j)
    groups.sort(key=lambda g: -sum(r["dur"] for r in g))
    cents = [np.mean([r["emb"] for r in g], 0) for g in groups]
    for r in rows:
        sims = [float(r["emb"] @ c / np.linalg.norm(c)) for c in cents]
        r["voice"] = f"V{int(np.argmax(sims))}"
        r["voice_sim"] = round(max(sims), 2)
    stats = []
    for gi, g in enumerate(groups):
        mem = [r for r in rows if r["voice"] == f"V{gi}"]
        f0s = [r["f0"] for r in mem if r["f0"]]
        stats.append({"voice": f"V{gi}", "phrases": len(mem), "speech_s": round(sum(r["dur"] for r in mem), 1),
                      "f0_median": round(float(np.median(f0s)), 0) if f0s else None,
                      "clips": sorted({r["clip"] for r in mem})})
    for r in rows:
        r.pop("emb")
    json.dump({"voices": stats, "phrases": rows}, open(out, "w"), indent=1)
    for s in stats:
        print(f"{s['voice']}: {s['speech_s']} s in {s['phrases']} phrases, f0 {s['f0_median']} Hz, clips {', '.join(c[3:] for c in s['clips'])}")


if __name__ == "__main__":
    main()
