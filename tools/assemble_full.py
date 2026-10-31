"""Build the final English clips for the full run (mp4 only, original file names, original order).

    python3 tools/assemble_full.py exchange/full media/full outputs/full [clip ...]

- Clips without lip-sync: original video stream copied untouched + English dialogue (AAC 320k).
- Clips with lip-sync: frame-exact rebuild; frames covered by completed sync-3 jobs come from the job
  output (for chained two-speaker shots, the last job of the chain), everything else is original.
- 87434 / 87646: reuse the approved test versions (identical source frames), 87646 = test 87646 + 87725.
Every output is checked to have exactly the source's frame count. Writes outputs/full/report.json.
"""
import glob
import json
import os
import subprocess
import sys

FPS = "24000/1001"
SPF = 2002
X264 = ["-c:v", "libx264", "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-r", FPS]
TEST_A = "deliverables/test1/alt_A_autodub"


def run(cmd):
    subprocess.run(cmd, check=True)


def nframes(path):
    return int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                               "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True).stdout)


def segments_for(clip, frames, jobs):
    """List of (first, last, source_path or None) covering 0..frames-1; None = original."""
    final = {}
    for j in jobs:  # a chained job (second speaker) replaces its parent on the same frame range
        key = (j["first_frame"], j["last_frame"])
        if key not in final or j.get("input_from") == final[key]["name"]:
            final[key] = j
    segs, cur = [], 0
    for (f0, f1), j in sorted(final.items()):
        if f0 > cur:
            segs.append((cur, f0 - 1, None))
        segs.append((f0, f1, j["file"]))
        cur = f1 + 1
    if cur < frames:
        segs.append((cur, frames - 1, None))
    return segs


def build(clip, src, ex, out_dir, jobs):
    name = os.path.basename(src)
    dst = os.path.join(out_dir, name)
    audio = os.path.join(ex, "en", f"{clip}_EN.wav")
    frames = nframes(src)
    if clip == "00087434":
        run(["ffmpeg", "-v", "error", "-y", "-i", glob.glob(f"{TEST_A}/*Splits00087434.mp4")[0], "-c", "copy",
             "-movflags", "+faststart", dst])
        return dst, frames, "reused approved test version"
    if clip == "00087646":
        a = glob.glob(f"{TEST_A}/*Splits00087646.mp4")[0]
        b = glob.glob(f"{TEST_A}/*Splits00087725.mp4")[0]
        fc = (f"[0:v]trim=start_frame=0:end_frame=79,setpts=PTS-STARTPTS,settb=AVTB,fps={FPS}[v0];"
              f"[1:v]trim=start_frame=0:end_frame=220,setpts=PTS-STARTPTS,settb=AVTB,fps={FPS}[v1];"
              f"[v0][v1]concat=n=2:v=1:a=0[v];"
              f"[0:a]atrim=end_sample={79 * SPF},asetpts=PTS-STARTPTS[a0];[1:a]asetpts=PTS-STARTPTS[a1];"
              f"[a0][a1]concat=n=2:v=0:a=1[a]")
        run(["ffmpeg", "-v", "error", "-y", "-i", a, "-i", b, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
             *X264, "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", dst])
        return dst, frames, "reused approved test versions (87646 + 87725)"
    segs = segments_for(clip, frames, jobs)
    if all(s[2] is None for s in segs):
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", dst])
        return dst, frames, "English audio, picture untouched"
    inputs, chains, labels = ["-i", src], [], []
    for k, (f0, f1, path) in enumerate(segs):
        n = f1 - f0 + 1
        if path:
            inputs += ["-i", os.path.join(ex, path)]
            idx, start = len(inputs) // 2 - 1, 0
        else:
            idx, start = 0, f0
        chains.append(f"[{idx}:v]trim=start_frame={start}:end_frame={start + n},setpts=PTS-STARTPTS,"
                      f"scale=1920:1080:flags=lanczos,format=yuv420p,settb=AVTB,fps={FPS}[s{k}]")
        labels.append(f"[s{k}]")
    fc = ";".join(chains) + f";{''.join(labels)}concat=n={len(labels)}:v=1:a=0[v]"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-i", audio, "-filter_complex", fc, "-map", "[v]",
         "-map", f"{len(inputs) // 2}:a", *X264, "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest",
         "-movflags", "+faststart", dst])
    synced = [f"{f0}-{f1}" for f0, f1, p in segs if p]
    return dst, frames, "lip-synced frames " + ", ".join(synced)


def main():
    ex, media, out = sys.argv[1:4]
    only = set(sys.argv[4:])
    os.makedirs(out, exist_ok=True)
    man_p = os.path.join(ex, "lipsync", "manifest.json")
    done = [j for j in (json.load(open(man_p)) if os.path.exists(man_p) else [])
            if j.get("status") == "COMPLETED" and os.path.exists(os.path.join(ex, j.get("file", "x")))]
    rep_p = os.path.join(out, "report.json")
    report = {r["clip"]: r for r in (json.load(open(rep_p)) if os.path.exists(rep_p) else [])}
    for c in json.load(open(os.path.join(ex, "clips.json"))):
        clip = c["clip"]
        if only and clip not in only:
            continue
        src = glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0]
        dst, frames, how = build(clip, src, ex, out, [j for j in done if j["clip"] == clip])
        got = nframes(dst)
        report[clip] = {"clip": clip, "file": os.path.basename(dst), "frames": got, "source_frames": frames,
                        "ok": got == frames, "how": how}
        print(f"{clip}: {'OK' if got == frames else f'FRAME MISMATCH {got}/{frames}'} - {how}", flush=True)
    json.dump([report[k] for k in sorted(report)], open(rep_p, "w"), indent=1)


if __name__ == "__main__":
    main()
