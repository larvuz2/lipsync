"""Turn exchange/full/plan.json (per-clip lip-sync decisions) into lipsync_jobs.json + job audio.

    python3 tools/build_lipsync_jobs.py exchange/full [clip ...]

plan.json: {"<clip>": {"jobs": [{"first": F, "last": L, "face": [frame_abs, x, y],
                                 "keep": [[t0, t1], ...]?, "after": "<job name>"?}], "note": "..."}}
- frames are absolute in the clip; face frame is converted to job-relative.
- "keep": only English speech belonging to these Hungarian phrase windows stays in the job audio
  (used when two people talk in one shot); other English speech is muted.
- "after": chain this job onto another job's output (second speaker in the same shot).
Writes exchange/full/lipsync_audio/<name>.wav and appends/replaces entries in lipsync_jobs.json.
"""
import json
import os
import subprocess
import sys

import numpy as np

SR, SPF = 48000, 2002


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def phrases(x, hop=480):
    n = len(x) // hop
    db = np.array([20 * np.log10(np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(n)])
    on = db > max(-52, db.max() - 32)
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
        if out and (a - out[-1][1]) * hop / SR < 0.18:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a * hop / SR, b * hop / SR) for a, b in out]


def overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def main():
    ex = sys.argv[1]
    only = set(sys.argv[2:])
    plan = json.load(open(os.path.join(ex, "plan.json")))
    an = {r["clip"]: r for r in json.load(open(os.path.join(ex, "analysis", "analysis.json")))}
    jobs_p = os.path.join(ex, "lipsync_jobs.json")
    jobs = {j["name"]: j for j in (json.load(open(jobs_p)) if os.path.exists(jobs_p) else [])}
    os.makedirs(os.path.join(ex, "lipsync_audio"), exist_ok=True)
    for clip, cfg in plan.items():
        if only and clip not in only:
            continue
        en = load(os.path.join(ex, "en", f"{clip}_EN.wav"))
        hu_ph = [(p["start"], p["end"]) for p in an[clip]["phrases"]]
        for k, j in enumerate(cfg.get("jobs", [])):
            f0, f1 = j["first"], j["last"]
            name = f"{clip}_f{f0}-{f1}" + (f"_s{k}" if j.get("keep") else "")
            x = en.copy()
            if j.get("keep"):
                keep = [tuple(w) for w in j["keep"]]
                other = [p for p in hu_ph if not any(overlap(p, w) > 0.05 for w in keep)]
                mask = np.zeros(len(x))
                for seg in phrases(en):
                    if sum(overlap(seg, w) for w in keep) >= sum(overlap(seg, w) for w in other) and \
                            sum(overlap(seg, w) for w in keep) > 0:
                        a, b = int(seg[0] * SR), int(seg[1] * SR)
                        mask[max(0, a - 1440):b + 1440] = 1  # 30 ms margins
                ramp = np.convolve(mask, np.ones(960) / 960, mode="same")  # soft edges
                x *= ramp
            need = (f1 - f0 + 1) * SPF
            seg = x[f0 * SPF:f0 * SPF + need + SPF]
            seg = np.pad(seg, (0, need + SPF - len(seg)))
            rel = f"lipsync_audio/{name}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                            "-c:a", "pcm_s24le", os.path.join(ex, rel)],
                           input=np.stack([seg, seg], 1).astype(np.float32).tobytes(), check=True)
            fr, fx, fy = j["face"]
            entry = {"name": name, "clip": clip, "first_frame": f0, "last_frame": f1, "audio": rel,
                     "face": {"frame": fr - f0, "xy": [fx, fy]}}
            if j.get("after"):
                entry["input_from"] = j["after"]
            jobs[name] = entry
            print(name, entry["face"], "chain<-" + j["after"] if j.get("after") else "")
    json.dump(list(jobs.values()), open(jobs_p, "w"), indent=1)
    tot = sum(j["last_frame"] - j["first_frame"] + 1 for j in jobs.values())
    print(f"{len(jobs)} jobs, {tot} frames = {tot * 1001 / 24000:.1f} s")


if __name__ == "__main__":
    main()
