"""Assemble a ~10 s voice-option sample for Hunyadi from three of his shots (final EN clips), his lines replaced by
an option's takes, each fitted onto the span of the current (lip-synced) English line so the mouths still match.

    python3 tools/military_render.py <option: current|clyde|designed|own> <out.mp4> "<eyebrow>" "<name>" "<sub>"
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from fixes_local import SR, load, pitch_shift, squeeze_pauses, stretch, trim  # noqa: E402
from melody_labels import fonts  # noqa: E402
from pp_labels import label  # noqa: E402

W, H = 1920, 1080
FPS = 24000 / 1001
D = "deliverables/full"
# (clip, window start, window end, [(line, span of the current lip-synced English line)]) - spans from a 10 ms
# energy scan of the delivered dialogue track (-50 dB): his lines sit between silences, nobody else speaks here
SEGS = [("00102229", 9.90, 15.35, [("P1", (10.21, 11.78)), ("P2", (11.91, 13.37)), ("P3", (14.17, 14.90))]),
        ("00101704", 0.30, 3.00, [("P4", (0.64, 2.90))]),
        ("00103280", 5.90, 8.70, [("P5", (6.25, 7.98))])]
MAX_SPEED = 1.3
OWN_PITCH = 2 ** (-1.5 / 12)          # option "own": 1.5 semitones lower


def clip(c):
    return glob.glob(f"{D}/*Splits{c}_EN.mp4")[0]


def spans(x, t0, t1, n):
    """Speech spans (s, clip time) inside [t0, t1]: 10 ms frames above -50 dB, gaps < 0.15 s merged; expect n."""
    hop = SR // 100
    a, b = int(t0 * 100), int(t1 * 100)
    db = np.array([20 * np.log10(np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(a, b)])
    on = db > -50
    segs, k = [], 0
    while k < len(on):
        if on[k]:
            j = k
            while j < len(on) and on[j]:
                j += 1
            segs.append([k, j]); k = j
        else:
            k += 1
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < 15:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    merged = [s for s in merged if s[1] - s[0] >= 8]
    assert len(merged) == n, (t0, merged)
    return [((a + s) / 100, (a + e) / 100) for s, e in merged]


def toughen(y):
    """The current voice made deeper and harder, timing untouched: PSOLA pitch -2 semitones, +4 dB chest (120-350 Hz),
    -2 dB above 6 kHz, soft saturation, loudness back to the original."""
    from scipy.signal import butter, sosfilt
    rms = np.sqrt(np.mean(y ** 2)) + 1e-9
    z = pitch_shift(y, 2 ** (-2 / 12))
    chest = sosfilt(butter(2, [120, 350], btype="band", fs=SR, output="sos"), z)
    air = sosfilt(butter(2, 6000, btype="high", fs=SR, output="sos"), z)
    z = z + 0.58 * chest - 0.2 * air
    g = 3.0 / (np.max(np.abs(z)) + 1e-9)
    z = np.tanh(z * g) / g
    z *= rms / (np.sqrt(np.mean(z ** 2)) + 1e-9)
    f = int(0.01 * SR)
    z[:f] *= np.linspace(0, 1, f); z[-f:] *= np.linspace(1, 0, f)
    return z.astype(np.float32)


def best_take(opt, lid, length):
    takes = [t for t in json.load(open(f"work/military/takes/{opt}.json"))["takes"] if t["line"] == lid]
    cands = []
    for t in takes:
        y = squeeze_pauses(trim(load(t["file"]), rel=38), keep=0.07)   # TTS comma pauses the dub doesn't have
        if opt == "own":
            y = pitch_shift(y, OWN_PITCH)
        cands.append((abs(np.log(len(y) / length)), t["file"], y))
    return min(cands, key=lambda c: c[0])


def main():
    opt, out, eb, name, sub = sys.argv[1:6]
    report, audio_parts, video_parts = [], [], []
    tmp = f"work/military/tmp_{opt}"
    os.makedirs(tmp, exist_ok=True)
    # one timeline: the three windows back to back; a line may run past its shot into the next window's silence
    # (J-cut), never into his next line
    lines, off = [], 0.0
    for c, t0, t1, lids in SEGS:
        x = load(clip(c))
        audio_parts.append(x[int(t0 * SR):int(t1 * SR)].copy())
        for lid, (s, e) in lids:
            lines.append((c, lid, s, e, off + s - t0, x[int(s * SR):int(e * SR)]))
        off += t1 - t0
        v = f"{tmp}/{c}.mkv"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-i", clip(c), "-t", f"{t1 - t0:.3f}",
                        "-an", "-c:v", "ffv1", "-pix_fmt", "yuv420p", v], check=True)
        video_parts.append(v)
    audio = np.concatenate(audio_parts)
    total = len(audio)
    if opt == "processed":
        for c, lid, s, e, g, ref in lines:
            a, b = int((g - 0.03) * SR), int((g + e - s + 0.03) * SR)
            audio[a:b] = toughen(audio[a:b])
            report.append({"clip": c, "line": lid, "span": [s, e], "processing": "pitch -2 st, chest EQ, drive"})
    elif opt != "current":
        for i, (c, lid, s, e, g, ref) in enumerate(lines):
            nxt = lines[i + 1][4] if i + 1 < len(lines) else total / SR
            avail = int((nxt - g - 0.06) * SR)
            n = len(ref)
            err, f, y = best_take(opt, lid, n)
            f_rat = float(np.clip(n / len(y), 0.80, 1.20))           # keep a natural pace
            if len(y) * f_rat > avail:
                f_rat = max(avail / len(y), 1 / MAX_SPEED)
            y = stretch(y, int(len(y) * f_rat))[:avail]
            y *= np.sqrt(np.mean(ref ** 2)) / (np.sqrt(np.mean(y ** 2)) + 1e-9)
            fade = int(0.01 * SR)
            y[:fade] *= np.linspace(0, 1, fade); y[-fade:] *= np.linspace(1, 0, fade)
            a = int(g * SR)
            audio[max(0, a - int(0.03 * SR)):min(total, a + n + int(0.03 * SR))] = 0   # old line out
            audio[a:a + len(y)] += y                                                   # new take in
            report.append({"clip": c, "line": lid, "span": [s, e], "take": f, "speed": round(1 / f_rat, 2),
                           "runs_over_s": round(max(0, len(y) - n) / SR, 2),
                           "cut_short": len(y) * 1.0 < int(len(stretch(y, len(y)))) and False})
    wav = f"{tmp}/audio.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-ac", "2",
                    "-c:a", "pcm_s24le", wav], input=audio.astype(np.float32).tobytes(), check=True)
    lst = f"{tmp}/list.txt"
    open(lst, "w").write("".join(f"file '{os.path.abspath(v)}'\n" for v in video_parts))
    F = fonts("work/melody/fonts")
    lab = label(eb, name, sub, F)
    lab.save(f"{tmp}/label.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
                    "-i", f"{tmp}/label.png", "-i", "work/pp/labels/brand.png",
                    "-filter_complex", "[0:v][2:v]overlay=40:36[a];[a][3:v]overlay=W-w-40:36[v]",
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out],
                   check=True)
    json.dump(report, open(out + ".json", "w"), indent=1)
    for r in report:
        print(r)
    print("wrote", out, f"{len(audio) / SR:.2f} s")


if __name__ == "__main__":
    main()
