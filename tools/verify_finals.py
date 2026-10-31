"""Final checks on every delivered clip.

    python3 tools/verify_finals.py exchange/full media/full outputs/full

Per clip: same file name as the source, frame count equal to the source, 1920x1080 at 24000/1001,
one AAC 48 kHz audio stream whose length matches the picture, and audio that is the corrected English
track (loudness-envelope correlation with en/<clip>_EN.wav; 87434/87646 compare against the approved
test audio instead). Writes outputs/full/verify.json.
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                          "stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,sample_rate,duration",
                          "-of", "json", path], capture_output=True, text=True).stdout
    return json.loads(out)["streams"]


def env(path, sr=8000, hop=80):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    n = len(x) // hop
    return np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, 1) + 1e-12)


def main():
    ex, media, out = sys.argv[1:4]
    res, bad = [], 0
    for c in json.load(open(os.path.join(ex, "clips.json"))):
        clip = c["clip"]
        src = glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0]
        dst = os.path.join(out, os.path.basename(src))
        r = {"clip": clip, "file": os.path.basename(dst), "exists": os.path.exists(dst)}
        if r["exists"]:
            s = probe(dst)
            v = [x for x in s if x["codec_type"] == "video"][0]
            a = [x for x in s if x["codec_type"] == "audio"]
            r["frames"], r["source_frames"] = int(v["nb_read_frames"]), int(c["frames"])
            r["video_ok"] = (r["frames"] == r["source_frames"] and v["width"] == 1920 and v["height"] == 1080
                             and v["r_frame_rate"] == "24000/1001")
            r["audio_ok"] = len(a) == 1 and a[0]["codec_name"] == "aac" and a[0]["sample_rate"] == "48000"
            vdur = r["frames"] * 1001 / 24000
            r["av_diff_ms"] = round((float(a[0]["duration"]) - vdur) * 1000) if a else None
            ref = (glob.glob(f"deliverables/test1/alt_A_autodub/*Splits{clip}.mp4") or [None])[0] \
                if clip in ("00087434", "00087646") else os.path.join(ex, "en", f"{clip}_EN.wav")
            if ref:
                e1, e2 = env(dst), env(ref)
                n = min(len(e1), len(e2))
                r["english_match"] = round(float(np.corrcoef(np.log(e1[:n]), np.log(e2[:n]))[0, 1]), 3)
            ok = r["video_ok"] and r["audio_ok"] and abs(r["av_diff_ms"] or 0) <= 60 and r.get("english_match", 1) > 0.9
        else:
            ok = False
        r["ok"] = bool(ok)
        bad += not ok
        res.append(r)
        print(f"{clip}: {'OK ' if ok else 'BAD'} {json.dumps({k: v for k, v in r.items() if k not in ('clip', 'file')})}",
              flush=True)
    json.dump(res, open(os.path.join(out, "verify.json"), "w"), indent=1)
    print(f"{len(res) - bad}/{len(res)} clips pass")


if __name__ == "__main__":
    main()
