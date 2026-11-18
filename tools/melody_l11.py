"""Melody EP101 demo: Portuguese line 11 ("Não, esquece.") as its own take in Melody's cloned voice.

    python3 tools/melody_l11.py work/melody work/melody/dub/tts_l11_0_a.mp3

In the Portuguese dub, Melody's "Não" ran into the end of Layla's line, so the cut between Hebrew and Portuguese
clipped it. This take replaces it: the pause after "Não" is shortened, the line is fitted (Praat PSOLA, pitch kept)
into 60.17-61.02 s, before line 12, and set to the dub's level. Writes work/melody/dub/l11_pt.wav (line only).
"""
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fixes_local import stretch  # noqa: E402

SR = 48000
SLOT = (60.17, 61.02)
PAUSE = (0.40, 0.62)  # in the take: decay after "Não" to the start of "esquece"
TARGET_DB = -21.2     # level of line 11 in the Portuguese dub


def main():
    w, take = sys.argv[1], sys.argv[2]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", take, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).copy()
    on = np.flatnonzero(np.abs(x) > 0.01)
    a, b = int(PAUSE[0] * SR), int(PAUSE[1] * SR)
    xf = int(0.02 * SR)
    head, tail = x[:a + xf].copy(), x[b:].copy()
    r = np.linspace(1, 0, xf)
    head[-xf:] = head[-xf:] * r + tail[:xf] * (1 - r)
    y = np.concatenate([head, tail[xf:]])
    on = np.flatnonzero(np.abs(y) > 0.01)
    y = y[max(0, on[0] - int(0.01 * SR)):on[-1] + int(0.04 * SR)]
    y = stretch(y, int((SLOT[1] - SLOT[0]) * SR))
    rms = np.sqrt(np.mean(y[np.abs(y) > 0.005] ** 2))
    y = y * (10 ** (TARGET_DB / 20) / (rms + 1e-9))
    f = int(0.008 * SR)
    y[:f] *= np.linspace(0, 1, f)
    y[-f:] *= np.linspace(1, 0, f)
    out = os.path.join(w, "dub", "l11_pt.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-ac", "2",
                    "-c:a", "pcm_s24le", out], input=y.astype(np.float32).tobytes(), check=True)
    print(out, f"{len(y) / SR:.2f}s, peak {20 * np.log10(np.abs(y).max()):.1f} dBFS")


if __name__ == "__main__":
    main()
