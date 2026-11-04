"""Put the exact audio a finished lip-sync job was made from back into a clip's English track.

    python3 tools/restore_job_audio.py exchange/full <clip> <job_name>:<start>-<end> [...]

Use it when a line was re-rendered with identical timing (so the finished lip sync still fits) but its
waveform differs slightly: inside [start, end] (seconds, clip time) the track is replaced with the job's own
audio (lipsync_audio/<job_name>.wav), with 10 ms cross-fades at both ends. Run it after fixes_local apply.
"""
import json
import os
import sys

import numpy as np
import soundfile as sf

FPS = 24000 / 1001


def main():
    ex, clip = sys.argv[1], sys.argv[2]
    p = os.path.join(ex, "en", f"{clip}_EN.wav")
    x, sr = sf.read(p, always_2d=True)
    jobs = {j["name"]: j for j in json.load(open(os.path.join(ex, "lipsync_jobs.json")))}
    man = {m["name"]: m for m in json.load(open(os.path.join(ex, "lipsync", "manifest.json")))}
    for arg in sys.argv[3:]:
        name, span = arg.split(":")
        a, b = (float(v) for v in span.split("-"))
        m = man[name]
        assert m.get("status") == "COMPLETED", name
        y, sr2 = sf.read(os.path.join(ex, m["audio"]), always_2d=True)
        assert sr2 == sr
        off = round(m["first_frame"] / FPS * sr)
        i0, i1 = int(a * sr), int(b * sr)
        seg = y[i0 - off:i1 - off, :x.shape[1]]
        n = int(0.01 * sr)
        w = np.ones(i1 - i0)
        w[:n] = np.linspace(0, 1, n)
        w[-n:] = np.linspace(1, 0, n)
        x[i0:i1] = x[i0:i1] * (1 - w[:, None]) + seg * w[:, None]
        print(f"{clip}: {a:.2f}-{b:.2f} s restored from {name}")
    sf.write(p, x, sr, subtype="PCM_24")


if __name__ == "__main__":
    main()
