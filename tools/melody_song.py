"""Melody EP101 demo: sing the French line on Melody's original melody.

    python3 tools/melody_song.py work/melody <take.mp3> [out.wav]

The take is spoken French ("Mon avenir... c'est aujourd'hui.") in Melody's cloned voice. Each of its 8 syllables
(mo-na-ve-nir / cè-tau-jour-dhui, found by forced alignment) is stretched onto one of the 8 sung notes of the original
("Mi futuro" 81.03-81.78 s, "...es hoy" 82.41-83.13 s) and given that note's exact pitch contour (glides and vibrato
included) with PSOLA in Praat. Loudness per note follows the original vocal. Output: 48 kHz stereo, clip time
80.90-83.30 s (so it can be dropped into the dialogue stem at 80.90).
"""
import os
import subprocess
import sys

import librosa
import numpy as np
import parselmouth
from parselmouth.praat import call

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import align as al  # noqa: E402

SR = 48000
OUT0, OUT1 = 80.90, 83.30
NOTES = [[(81.03, 81.18), (81.19, 81.31), (81.32, 81.43), (81.44, 81.80)],
         [(82.41, 82.53), (82.54, 82.66), (82.67, 82.88), (82.92, 83.14)]]
WORDS = ["mon", "avenir", "cest", "aujourdhui"]
# syllable starts as (word index, char index); a syllable ends where the next one starts (or at its word's end)
SYL = [[(0, 0), (0, 2), (1, 1), (1, 3)], [(2, 0), (2, 3), (3, 2), (3, 6)]]


def load(p, a=None, b=None, sr=SR):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{a:.3f}", "-to", f"{b:.3f}"] if a is not None else [])
    raw = subprocess.run(cmd + ["-i", p, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True,
                         check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def char_spans(x):
    m = al._model()
    torch, ta = m["torch"], m["ta"]
    wav = ta.functional.resample(torch.from_numpy(x)[None], SR, m["sr"])
    with torch.inference_mode():
        em, _ = m["model"](wav)
    spans = m["aligner"](em[0], m["tok"](WORDS))
    ratio = wav.shape[1] / em.shape[1] / m["sr"]
    return [[(s.start * ratio, s.end * ratio) for s in w] for w in spans]


def target_f0(vocal, a, b):
    """Original sung pitch (Hz) every 5 ms between a and b (clip time); NaN where unvoiced."""
    y = load(vocal, a - 0.1, b + 0.1, 16000)
    f0, vf, _ = librosa.pyin(y, fmin=150, fmax=900, sr=16000, frame_length=1024, hop_length=80)
    t = a - 0.1 + np.arange(len(f0)) * 0.005
    f0[~vf] = np.nan
    return t, f0


def sing_phrase(x, spans, syl, notes, vocal):
    """PSOLA: one phrase of the take -> its notes. Returns (audio, out_start)."""
    word_end = lambda wi: spans[wi][-1][1]
    starts = [spans[wi][ci][0] for wi, ci in syl]
    ends = starts[1:] + [word_end(syl[-1][0])]
    src0, src1 = starts[0] - 0.03, ends[-1] + 0.06
    seg = x[int(src0 * SR):int(src1 * SR)]
    snd = parselmouth.Sound(seg.astype(np.float64), sampling_frequency=SR)
    man = call(snd, "To Manipulation", 0.005, 120, 700)
    dur = call("Create DurationTier", "dur", 0, src1 - src0)
    pit = call("Create PitchTier", "pit", 0, src1 - src0)
    t_f0, f0 = target_f0(vocal, notes[0][0], notes[-1][1])
    ratios = []
    for (s, e), (t, u) in zip(zip(starts, ends), notes):
        r = (u - t) / max(e - s, 0.02)
        ratios.append(r)
        s_, e_ = s - src0, e - src0
        call(dur, "Add point", s_ + 0.001, r)
        call(dur, "Add point", e_ - 0.001, r)
        for tt, ff in zip(t_f0, f0):  # target pitch, mapped back into the take's time axis
            if t <= tt <= u and np.isfinite(ff):
                call(pit, "Add point", s_ + (tt - t) / r, float(ff))
    call(dur, "Add point", 0.0005, 1.0)
    call(dur, "Add point", src1 - src0 - 0.0005, 1.0)
    call([man, dur], "Replace duration tier")
    call([man, pit], "Replace pitch tier")
    out = call(man, "Get resynthesis (overlap-add)")
    y = out.values[0].astype(np.float32)
    # the output starts at the take's src0, i.e. 0.03 s (unstretched) before the first syllable onset
    return y, notes[0][0] - 0.03, ratios


def main():
    w, take = sys.argv[1], sys.argv[2]
    out_p = sys.argv[3] if len(sys.argv) > 3 else os.path.join(w, "song", "song_fr.wav")
    vocal = os.path.join(w, "stems", "fragmento_vocals.wav")
    x = load(take)
    x = x / (np.abs(x).max() + 1e-9) * 0.5
    spans = char_spans(x)
    n = int((OUT1 - OUT0) * SR)
    res = np.zeros(n, np.float32)
    orig = load(vocal, OUT0, OUT1)
    for syl, notes in zip(SYL, NOTES):
        y, t0, ratios = sing_phrase(x, spans, syl, notes, vocal)
        # loudness per note follows the original vocal (smoothed), capped to +-12 dB of the take's own level
        k0 = int((t0 - OUT0) * SR)
        y = y[:max(0, n - k0)]
        fr = 0.03
        for (t, u) in notes:
            a, b = int((t - OUT0) * SR), int((u - OUT0) * SR)
            ya, yb = max(0, a - k0), max(0, b - k0)
            if yb <= ya:
                continue
            ro = np.sqrt(np.mean(orig[a:b] ** 2)) + 1e-6
            ry = np.sqrt(np.mean(y[ya:yb] ** 2)) + 1e-6
            g = float(np.clip(ro / ry, 10 ** (-12 / 20), 10 ** (12 / 20)))
            env = np.ones(len(y), np.float32)
            env[ya:yb] = g
            y = y * np.convolve(env, np.ones(int(fr * SR)) / int(fr * SR), mode="same")
        res[k0:k0 + len(y)] += y
        print("phrase", [f"{r:.2f}" for r in ratios])
    fade = int(0.03 * SR)
    res[:fade] *= np.linspace(0, 1, fade)
    res[-fade:] *= np.linspace(1, 0, fade)
    full = np.zeros(int(OUT1 * SR) + SR, np.float32)
    full[int(OUT0 * SR):int(OUT0 * SR) + n] = res
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-ac", "2",
                    "-c:a", "pcm_s24le", out_p], input=full.tobytes(), check=True)
    print("wrote", out_p)


if __name__ == "__main__":
    main()
