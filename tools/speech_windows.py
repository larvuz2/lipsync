"""Find exact speech phrases in a dialogue-only track from its loudness (10 ms resolution).

    python3 tools/speech_windows.py "media/LIP SYNC TEST" 87434 87646 87725
"""
import glob
import os
import subprocess
import sys

import numpy as np

SR, HOP = 16000, 160  # 10 ms


def phrases(path, floor_db=-52.0, rel_db=32.0, min_gap=0.18, min_len=0.08):
    x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR),
                                      "-f", "f32le", "-"], capture_output=True, check=True).stdout, dtype=np.float32)
    n = len(x) // HOP
    db = np.array([20 * np.log10(np.sqrt(np.mean(x[i * HOP:(i + 1) * HOP] ** 2)) + 1e-9) for i in range(n)])
    # smooth over 30 ms
    db = np.convolve(db, np.ones(3) / 3, mode="same")
    thr = max(floor_db, db.max() - rel_db)
    on = db > thr
    segs, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        if not v and start is not None:
            segs.append([start, i]); start = None
    if start is not None:
        segs.append([start, n])
    merged = []
    for s in segs:
        if merged and (s[0] - merged[-1][1]) * HOP / SR < min_gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    out = [(round(a * HOP / SR, 2), round(b * HOP / SR, 2)) for a, b in merged if (b - a) * HOP / SR >= min_len]
    return out, len(x) / SR, thr


if __name__ == "__main__":
    for clip in sys.argv[2:]:
        p = glob.glob(os.path.join(sys.argv[1], f"*{clip}.mp4"))[0]
        segs, dur, thr = phrases(p)
        print(clip, f"dur={dur:.3f} thr={thr:.0f}dB", " ".join(f"[{a:.2f}-{b:.2f}]" for a, b in segs))
