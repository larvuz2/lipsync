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
import glob
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

ZOOM_OUT = 1080

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


def zoom_track(ex, clip, f0, f1, pin, zs, name):
    """Per-frame square windows (size zs) centred on the tracked face, smoothed; writes the enlarged input video
    lipsync_zoom/<name>.mp4 and the windows lipsync_zoom/<name>.json. Returns the job fields."""
    import cv2
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import assemble_masked as am
    media = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ex))), "media", "full")
    srcv = glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0]
    det = cv2.FaceDetectorYN.create(f"{am.MODELS}/yunet.onnx", "", (am.W, am.H), 0.4)
    fr, fx, fy = pin
    boxes = am.track(srcv, f0, f1, fr, (fx, fy), det)
    ks = sorted(boxes)
    cx = np.array([np.interp(k, ks, [boxes[q][0] + boxes[q][2] / 2 for q in ks]) for k in range(f0, f1 + 1)])
    cy = np.array([np.interp(k, ks, [boxes[q][1] + boxes[q][3] * 0.6 for q in ks]) for k in range(f0, f1 + 1)])
    w = 9  # smooth the path so the crop does not shake
    pad = lambda a: np.convolve(np.pad(a, w // 2, mode="edge"), np.ones(w) / w, mode="valid")
    cx, cy = pad(cx), pad(cy)
    wins = [[int(np.clip(round(x - zs / 2), 0, am.W - zs)), int(np.clip(round(y - zs / 2), 0, am.H - zs))]
            for x, y in zip(cx, cy)]
    os.makedirs(os.path.join(ex, "lipsync_zoom"), exist_ok=True)
    rel_v, rel_w = f"lipsync_zoom/{name}.mp4", f"lipsync_zoom/{name}.json"
    json.dump({"size": zs, "first": f0, "windows": wins}, open(os.path.join(ex, rel_w), "w"))
    if not os.path.exists(os.path.join(ex, rel_v)):
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s",
                                f"{ZOOM_OUT}x{ZOOM_OUT}", "-r", "24000/1001", "-i", "-", "-an", "-c:v", "libx264", "-crf",
                                "12", "-preset", "slow", "-bf", "0", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
                                "-color_trc", "bt709", "-colorspace", "bt709", "-r", "24000/1001",
                                os.path.join(ex, rel_v)], stdin=subprocess.PIPE)
        cap = cv2.VideoCapture(srcv)
        cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
        for (zx, zy) in wins:
            ok, im = cap.read()
            crop = cv2.resize(im[zy:zy + zs, zx:zx + zs], (ZOOM_OUT, ZOOM_OUT), interpolation=cv2.INTER_LANCZOS4)
            enc.stdin.write(crop.tobytes())
        enc.stdin.close()
        enc.wait()
    kz = ZOOM_OUT / zs
    zx, zy = wins[fr - f0]
    return {"zoom": {"size": zs, "file": rel_w}, "input_video": rel_v,
            "face": {"frame": fr - f0, "xy": [round((fx - zx) * kz), round((fy - zy) * kz)]}}


def main():
    ex = sys.argv[1]
    only = set(sys.argv[2:])
    plan = json.load(open(os.path.join(ex, "plan.json")))
    an = {r["clip"]: r for r in json.load(open(os.path.join(ex, "analysis", "analysis.json")))}
    tr_p = os.path.join(ex, "transcripts_en_final.json")  # word timings of the (fixed) English tracks
    tr = json.load(open(tr_p)) if os.path.exists(tr_p) else json.load(open(os.path.join(ex, "transcripts.json")))
    jobs_p = os.path.join(ex, "lipsync_jobs.json")
    old = {j["name"]: j for j in (json.load(open(jobs_p)) if os.path.exists(jobs_p) else [])}
    man_p = os.path.join(ex, "lipsync", "manifest.json")
    done = {m["name"]: m for m in (json.load(open(man_p)) if os.path.exists(man_p) else []) if m.get("status") == "COMPLETED"}
    # Rebuild from the plan: clips not selected keep their current jobs, selected clips are regenerated.
    jobs = {n: j for n, j in old.items() if only and j["clip"] not in only}
    os.makedirs(os.path.join(ex, "lipsync_audio"), exist_ok=True)
    for clip, cfg in plan.items():
        if only and clip not in only:
            continue
        en = load(os.path.join(ex, "en", f"{clip}_EN.wav"))
        # Hungarian sentence boundaries from the transcript (they separate speakers; loudness phrases can merge them)
        hu_ph = [(sg["start"], sg["end"]) for sg in tr.get(clip, {}).get("hu", [])] or \
            [(p["start"], p["end"]) for p in an.get(clip, {}).get("phrases", [])]
        names = {}
        for k, j in enumerate(cfg.get("jobs", [])):
            f0, f1 = j["first"], j["last"]
            base = f"{clip}_f{f0}-{f1}" + (f"_s{k}" if j.get("keep") or j.get("en_keep") else "") + \
                ("z" if j.get("zoom") else "")
            x = en.copy()
            if j.get("en_keep"):
                # exact English windows of this speaker (known placements of re-voiced lines)
                mask = np.zeros(len(x))
                for w0, w1 in j["en_keep"]:
                    mask[max(0, int(w0 * SR)):int(w1 * SR)] = 1
                x *= np.convolve(mask, np.ones(960) / 960, mode="same")
            elif j.get("keep"):
                keep = [tuple(w) for w in j["keep"]]
                other = [p for p in hu_ph if sum(overlap(p, w) for w in keep) < 0.5 * (p[1] - p[0])]
                mask = np.zeros(len(x))
                words = [w for sgm in tr.get(clip, {}).get("en", []) for w in sgm.get("words", [])]
                if words:
                    # word level: each English word goes to the Hungarian phrase it overlaps most / is nearest to
                    def dist(wd, ph):
                        return 0.0 if overlap(wd, ph) > 0 else min(abs(wd[0] - ph[1]), abs(ph[0] - wd[1]))
                    starts = sorted(w[0] for w in words)
                    for w0, w1, _txt, *_ in words:
                        wd = (w0, w1)
                        dk = min(dist(wd, ph) - overlap(wd, ph) for ph in keep)
                        do = min([dist(wd, ph) - overlap(wd, ph) for ph in other] or [9e9])
                        if dk <= do:
                            # Whisper word ends are often early: let the word run on up to 0.25 s, stopping
                            # 40 ms before the next word starts
                            nxt = min([s for s in starts if s > w0] or [9e9])
                            end = max(w1 + 0.04, min(w1 + 0.25, nxt - 0.04))
                            mask[max(0, int(w0 * SR) - 1920):int(end * SR)] = 1
                else:
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
            # The job name carries a fingerprint of its exact inputs, so a changed line forces a re-run
            # and stale outputs are never used. An unchanged legacy job keeps its old name (no re-run).
            q = np.round(seg * 32767).astype(np.int16)
            parent = names.get(j["after"]) if j.get("after") is not None else None
            fp = hashlib.sha1(q.tobytes() + json.dumps([j["face"], f0, f1, parent] +
                                                       ([j["zoom"]] if j.get("zoom") else [])).encode()).hexdigest()[:6]
            legacy = os.path.join(ex, "lipsync_audio", f"{base}.wav")
            name = f"{base}_{fp}"
            if base in old and os.path.exists(legacy) and not j.get("after"):
                prev = np.round(load(legacy)[:len(seg)] * 32767).astype(np.int16)
                if len(prev) == len(q) and np.abs(prev.astype(np.int32) - q).max() <= 1 and \
                        old[base]["face"] == {"frame": j["face"][0] - f0, "xy": j["face"][1:]}:
                    name = base
            if name not in done and not j.get("after") and not j.get("zoom"):
                # a finished job for the same shot, face and range whose audio differs only by rounding noise
                # (at most 8 LSB of 16-bit, about -72 dB, e.g. from rebuilding the mix) is reused, not re-run
                for cand in sorted(glob.glob(os.path.join(ex, "lipsync_audio", f"{base}_*.wav"))):
                    cn = os.path.basename(cand)[:-4]
                    if cn not in done or done[cn]["face"] != {"frame": j["face"][0] - f0, "xy": j["face"][1:]}:
                        continue
                    prev = np.round(load(cand)[:len(seg)] * 32767).astype(np.int16)
                    if len(prev) == len(q) and np.abs(prev.astype(np.int32) - q).max() <= 8:
                        name = cn
                        break
            names[k] = name
            rel = f"lipsync_audio/{name}.wav"
            if not os.path.exists(os.path.join(ex, rel)):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                                "-c:a", "pcm_s24le", os.path.join(ex, rel)],
                               input=np.stack([seg, seg], 1).astype(np.float32).tobytes(), check=True)
            fr, fx, fy = j["face"]
            entry = {"name": name, "clip": clip, "first_frame": f0, "last_frame": f1, "audio": rel,
                     "face": {"frame": fr - f0, "xy": [fx, fy]}}
            if parent:
                entry["input_from"] = parent
            if cfg.get("prepared_inputs") and not j.get("zoom"):
                # the runner does not have this clip's source: send the job's frames as a prepared input
                rel_v = f"lipsync_inputs/{name}.mp4"
                entry["input_video"] = rel_v
                if not os.path.exists(os.path.join(ex, rel_v)):
                    os.makedirs(os.path.join(ex, "lipsync_inputs"), exist_ok=True)
                    media = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ex))), "media", "full")
                    srcv = glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0]
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", srcv, "-vf",
                                    f"select='between(n,{f0},{f1})',setpts=N/FRAME_RATE/TB", "-an", "-r", "24000/1001",
                                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-bf", "0", "-pix_fmt", "yuv420p",
                                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                                    os.path.join(ex, rel_v)], check=True)
            if j.get("zoom") == "track":
                # small face that moves (camera or actor): a square window that follows the tracked face,
                # enlarged to ZOOM_OUT px; per-frame windows are saved next to the input video
                entry.update(zoom_track(ex, clip, f0, f1, (fr, fx, fy), int(j.get("zoom_size", 360)), name))
            elif j.get("zoom"):
                # face too small for lip sync in the full frame: send a fixed square crop around it, enlarged to
                # ZOOM_OUT px; the result is shrunk back and pasted in place at assembly
                zx, zy, zs = j["zoom"]
                kz = ZOOM_OUT / zs
                entry["zoom"] = [zx, zy, zs]
                entry["face"] = {"frame": fr - f0, "xy": [round((fx - zx) * kz), round((fy - zy) * kz)]}
                rel_v = f"lipsync_zoom/{name}.mp4"
                entry["input_video"] = rel_v
                if not os.path.exists(os.path.join(ex, rel_v)):
                    os.makedirs(os.path.join(ex, "lipsync_zoom"), exist_ok=True)
                    media = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ex))), "media", "full")
                    srcv = glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0]
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", srcv, "-vf",
                                    f"select='between(n,{f0},{f1})',setpts=N/FRAME_RATE/TB,crop={zs}:{zs}:{zx}:{zy},"
                                    f"scale={ZOOM_OUT}:{ZOOM_OUT}:flags=lanczos", "-an", "-r", "24000/1001",
                                    "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-bf", "0", "-pix_fmt", "yuv420p",
                                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                                    os.path.join(ex, rel_v)], check=True)
            jobs[name] = entry
            print(name, entry["face"], ("chain<-" + parent) if parent else "")
    json.dump(list(jobs.values()), open(jobs_p, "w"), indent=1)
    tot = sum(j["last_frame"] - j["first_frame"] + 1 for j in jobs.values())
    print(f"{len(jobs)} jobs, {tot} frames = {tot * 1001 / 24000:.1f} s")


if __name__ == "__main__":
    main()
