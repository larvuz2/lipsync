"""Build a finished English clip for a client re-split that spans several of our clips.

    python3 tools/build_resplit.py <split_number> <clip>:<first>-<last> [<clip>:<first>-<last> ...]
    e.g. python3 tools/build_resplit.py 00104359 00104240:119-220 00104461:0-233

Video: the frames of our finished clips (deliverables/full/*_EN.mp4), frame-exact, re-encoded once.
Audio: the English tracks (exchange/full/en/<clip>_EN.wav) cut at the same frame times, joined with 5 ms
crossfades. Writes outputs/full/<prefix>Splits<split_number>_EN.mp4 and checks the frame count.
"""
import glob
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000
FPS = 24000 / 1001
X264 = ["-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-r", "24000/1001"]


def audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def main():
    split, parts = sys.argv[1], sys.argv[2:]
    segs = []
    for p in parts:
        clip, rng = p.split(":")
        a, b = (int(v) for v in rng.split("-"))
        segs.append((clip, a, b))
    n = sum(b - a + 1 for _, a, b in segs)
    fins = {c: glob.glob(os.path.join(ROOT, "deliverables", "full", f"*Splits{c}_EN.mp4"))[0] for c, _, _ in segs}
    prefix = os.path.basename(fins[segs[0][0]]).split("Splits")[0]
    dst = os.path.join(ROOT, "outputs", "full", f"{prefix}Splits{split}_EN.mp4")
    tmp_v = dst[:-4] + "_v.mp4"
    tmp_a = dst[:-4] + "_a.wav"
    # video: select the frame ranges, concatenate, encode once
    inputs, filt = [], []
    for k, (c, a, b) in enumerate(segs):
        inputs += ["-i", fins[c]]
        filt.append(f"[{k}:v]select='between(n,{a},{b})',setpts=N/FRAME_RATE/TB[v{k}]")
    filt.append("".join(f"[v{k}]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[v]",
                    *X264, tmp_v], check=True)
    # audio: same frame times from the English tracks
    xf = int(0.005 * SR)
    out = None
    for c, a, b in segs:
        x = audio(os.path.join(ROOT, "exchange", "full", "en", f"{c}_EN.wav"))
        s0, s1 = round(a / FPS * SR), round((b + 1) / FPS * SR)
        y = x[s0:min(s1 + xf, len(x))]
        y = np.pad(y, ((0, max(0, s1 - s0 + xf - len(y))), (0, 0)))
        if out is None:
            out = y
        else:
            w = np.linspace(0, 1, xf)[:, None]
            out[-xf:] = out[-xf:] * (1 - w) + y[:xf] * w
            out = np.concatenate([out, y[xf:]])
    out = out[:round(n / FPS * SR)]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-c:a", "pcm_s24le", tmp_a], input=out.astype(np.float32).tobytes(), check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp_v, "-i", tmp_a, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart", dst],
                   check=True)
    os.remove(tmp_v)
    os.remove(tmp_a)
    got = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                              "stream=nb_read_frames", "-of", "csv=p=0", dst], capture_output=True, text=True).stdout)
    print(f"{os.path.basename(dst)}: {'OK' if got == n else f'FRAME MISMATCH {got}/{n}'} ({n} frames from "
          f"{', '.join(f'{c} {a}-{b}' for c, a, b in segs)})")


if __name__ == "__main__":
    main()
