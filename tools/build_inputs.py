"""Build the voice-clone sample and the auto-dub source from the line sheet.

    python3 tools/build_inputs.py "media/LIP SYNC TEST" data/test1_lines.json exchange/test1/inputs
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np

SR = 48000


def load(path, ch=1):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", str(ch), "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, ch).T.copy()


def save(path, x, codec="pcm_s24le"):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(x.shape[0]), "-i", "-",
                    "-c:a", codec, path], input=x.T.astype(np.float32).tobytes(), check=True)


src, sheet_path, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
sheet = json.load(open(sheet_path))
clip_path = lambda c: glob.glob(os.path.join(src, f"*{c}.mp4"))[0]

# 1) Voice-clone sample per speaker: every clean phrase joined with short gaps, peak at -3 dBFS.
for spk, cfg in sheet["speaker_voices"].items():
    parts, gap = [], np.zeros((1, int(0.35 * SR)), np.float32)
    for clip, wins in cfg["sample_windows"].items():
        x = load(clip_path(clip))
        for a, b in wins:
            seg = x[:, int(a * SR):int(b * SR)].copy()
            fade = int(0.01 * SR)
            seg[:, :fade] *= np.linspace(0, 1, fade)
            seg[:, -fade:] *= np.linspace(1, 0, fade)
            parts += [seg, gap]
    s = np.concatenate(parts, axis=1)
    s *= 10 ** (-3 / 20) / (np.abs(s).max() + 1e-9)
    save(os.path.join(out, f"voice_sample_{spk}.wav"), s)
    print(f"voice sample {spk}: {s.shape[1] / SR:.1f} s")

# 2) Auto-dub source: whole clips back to back (more speech helps the dubber clone the voice).
order = list(sheet["speaker_voices"]["trainer"]["sample_windows"].keys())
gap = np.zeros((2, int(0.6 * SR)), np.float32)
parts, offsets, t = [], {}, 0
for clip in order:
    x = load(clip_path(clip), ch=2)
    offsets[clip] = {"start_sample": t, "samples": x.shape[1]}
    parts += [x, gap]
    t += x.shape[1] + gap.shape[1]
d = np.concatenate(parts, axis=1)
save(os.path.join(out, "autodub_source.wav"), d, codec="pcm_s16le")
json.dump({"sample_rate": SR, "order": order, "offsets": offsets}, open(os.path.join(out, "autodub_offsets.json"), "w"), indent=1)
print(f"auto-dub source: {d.shape[1] / SR:.1f} s, clips {order}")
