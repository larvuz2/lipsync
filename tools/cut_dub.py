"""Cut the full auto-dub back into per-clip English dialogue tracks (same length as each clip's audio).

    python3 tools/cut_dub.py exchange/full media/full

Level: each clip is matched to the original dialogue on loud speech frames (90th percentile of 10 ms
loudness), so the English sits at the same level as the Hungarian did.
Writes exchange/full/en/<clip>_EN.wav (48 kHz stereo dual-mono) and en/levels.json.
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np

SR = 48000


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def fdb(x, hop=480):
    n = len(x) // hop
    return np.array([20 * np.log10(np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(max(n, 1))])


def main():
    ex, media = sys.argv[1:3]
    clips = json.load(open(os.path.join(ex, "clips.json")))
    man = json.load(open(os.path.join(ex, "dub", "manifest.json")))
    dub = load(os.path.join(ex, man["file"]))
    layout = json.load(open(os.path.join(ex, "inputs", "dub_layout.json")))
    scale = len(dub) / layout["total_samples"]
    os.makedirs(os.path.join(ex, "en"), exist_ok=True)
    report = {"scale": round(scale, 6), "clips": []}
    for c in clips:
        a = int(round(c["start_sample"] * scale))
        seg = dub[a:a + c["audio_samples"]].copy()
        seg = np.pad(seg, (0, c["audio_samples"] - len(seg)))
        hu = load(glob.glob(os.path.join(media, f"*Splits{c['clip']}.mp4"))[0])[:len(seg)]
        p_hu, p_en = np.percentile(fdb(hu), 90), np.percentile(fdb(seg), 90)
        gain = 10 ** ((p_hu - p_en) / 20) if p_en > -70 else 1.0
        gain = float(min(gain, 10 ** (12 / 20)))  # never boost more than +12 dB
        seg *= gain
        peak = float(np.abs(seg).max())
        if peak > 0.97:
            seg *= 0.97 / peak
        # English speech outside the clip's own Hungarian speech span hints at dub drift across clips.
        hu_on = fdb(hu) > max(-52, fdb(hu).max() - 32)
        en_on = fdb(seg) > max(-52, fdb(seg).max() - 32)
        spill = float(np.mean(en_on[~hu_on])) if (~hu_on).any() else 0.0
        out = os.path.join(ex, "en", f"{c['clip']}_EN.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-c:a", "pcm_s24le", out], input=np.stack([seg, seg], 1).astype(np.float32).tobytes(), check=True)
        report["clips"].append({"clip": c["clip"], "gain_db": round(20 * np.log10(gain), 1),
                                "hu_p90": round(float(p_hu), 1), "en_p90_after": round(float(np.percentile(fdb(seg), 90)), 1),
                                "en_speech_s": round(float(en_on.sum() * 0.01), 2), "hu_speech_s": round(float(hu_on.sum() * 0.01), 2),
                                "en_outside_hu_speech": round(spill, 2)})
    json.dump(report, open(os.path.join(ex, "en", "levels.json"), "w"), indent=1)
    print("scale", report["scale"])
    for r in report["clips"]:
        flag = "  <-- check" if r["en_speech_s"] < 0.3 * r["hu_speech_s"] or r["en_outside_hu_speech"] > 0.35 else ""
        print(f"{r['clip']}: gain {r['gain_db']:+.1f} dB  HU speech {r['hu_speech_s']:5.2f}s  EN speech {r['en_speech_s']:5.2f}s  EN outside HU {r['en_outside_hu_speech']:.2f}{flag}")


if __name__ == "__main__":
    main()
