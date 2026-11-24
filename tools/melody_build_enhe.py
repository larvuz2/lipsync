"""Melody EP101 demo, version 2: Spanish (original) -> English -> Hebrew. Voices, mix and lip-sync plan.

    python3 tools/melody_build_enhe.py work/melody exchange/melody_enhe

Script approved by the client: lines 1-2 Spanish (original audio), 3-7 English (native accent), 8-15 Hebrew (the
radio-studio scene and the ending; her humming stays original). Every line is voiced from the script in the girl's
own cloned voice (melody_tts_lines.py; the take with the most native accent / closest voice was picked), its long
pauses shortened, fitted to its slot with Praat PSOLA (pitch kept), placed where the line belongs in the scene and
set to the original line's loudness (EBU R128). The lip sync follows the new timing.
Writes:
  exchange/melody_enhe/en/00000101_EN.wav   new voices only (lip-sync job audio)
  work/melody/enhe/voice_final.wav           dialogue stem of the demo (original Spanish + humming + new lines)
  work/melody/enhe/final_mix.wav             voice_final + music/effects stem
  exchange/melody_enhe/plan.json, clips.json, transcripts.json, analysis/analysis.json
"""
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fixes_local import pitch_shift, stretch  # noqa: E402

SR = 48000
CLIP = "00000101"
# id, speaker, take, anchor = where the actress really starts this line (from the dialogue stem's energy, not
# Whisper's word times, which ran up to 0.5 s early), end of her original line. sync-3 keeps much of the original
# mouth rhythm, so each new line starts on her original start and is fitted toward her original length (0.75-1.12x);
# when the line before still runs, it starts right after it. "take:i" = phrase i of a take (split at its pauses),
# placed on her own phrase. Lines 4 and 6 use slightly shorter wordings ("I know, don't say it.", "With him, it's
# always more than fine.") so they fit her mouth.
LINES = [
    ("L3", "Layla", "L3_t1", 16.75, 18.20),
    ("L4", "Melody", "L4s_t3", 19.03, 20.42),
    ("L5a", "Melody", "L5_t0:0", 21.94, 22.66),
    ("L5b", "Melody", "L5_t0:1", 22.80, 23.53),
    ("L6", "Layla", "L6s_t0", 24.98, 26.74),
    ("L7", "Layla", "L7_t0", 26.80, 29.14),
    ("L8", "Melody", "L8_t2", 54.22, 54.57),
    ("L9", "Layla", "L9_t2", 57.17, 58.80),
    ("L10", "Layla", "L10_t0", 58.90, 59.85),
    ("L11", "Melody", "L11_t2", 59.52, 60.40),
    ("L12", "Melody", "L12_t2", 61.03, 63.51),
    ("L13", "Melody", "L13_t1", 63.85, 66.33),
    ("L14", "Melody", "L14_t0", 66.33, 67.27),
    ("L15a", "Melody", "L15_t2:0", 81.07, 81.65),
    ("L15b", "Melody", "L15_t2:1", 82.43, 83.14),
]
FIT = (0.75, 1.12)
GAP = 0.06           # at least this much after the previous line ends
OVERLAP_OK = 0.25    # an interruption (line 11 cutting line 10 off) may overlap the previous line this much
CUT = {"L10": 0.84}  # Melody cuts Layla off (as in the original): line 10 stops after "תבטיחי לי ש-" (s into the take)
SEGMENTS = [("en", 16.50, 30.20), ("he", 53.40, 69.30), ("he", 80.70, 83.96)]  # new voices replace the original here
MAX_PAUSE = 0.18      # longer pauses inside a take are shortened to this
END_BOOST_DB = 4.3    # the ending is said very softly in the original; keep the new line clearly audible
JOBS = [  # lip-sync shots: frames, face pin (frame, x, y), speaker
    # English two-shot: faces only ~200 px wide and turned 3/4 -> a tracked, enlarged crop of each face (as for small
    # faces in Rise of the Raven); Sync finds the speaking face in the crop itself (asd auto). Tested and not used:
    # the plain full-frame run, sync-3 with higher temperature (sync-3 ignores it) and lipsync-2-pro (weaker); the
    # real fix was the timing (see LINES).
    {"first": 393, "last": 725, "face": [457, 519, 361], "who": "Melody", "variant": "z", "zoom": "track",
     "zoom_size": 380, "asd": "auto", "steady": True, "fade_profile": True},  # she turns to full profile at 23.1 s
    {"first": 393, "last": 725, "face": [600, 1373, 153], "who": "Layla", "variant": "z", "zoom": "track",
     "zoom_size": 380, "asd": "auto", "steady": True},
    {"first": 1281, "last": 1329, "face": [1300, 874, 234], "who": "Melody"},
    {"first": 1363, "last": 1424, "face": [1394, 1563, 428], "who": "Layla"},
    {"first": 1425, "last": 1470, "face": [1448, 763, 408], "who": "Melody"},
    {"first": 1513, "last": 1640, "face": [1577, 761, 410], "who": "Melody"},
    {"first": 1925, "last": 2012, "face": [1944, 902, 462], "who": "Melody", "steady": True},
    # comparison on the re-timed English: lipsync-2-pro (moves the mouth more than sync-3, which keeps her smile)
    {"first": 393, "last": 725, "face": [457, 519, 361], "who": "Melody", "variant": "zp", "zoom": "track",
     "zoom_size": 380, "model": "lipsync-2-pro", "options": {"temperature": 0.8}, "use": False, "asd": "auto"},
    {"first": 393, "last": 725, "face": [600, 1373, 153], "who": "Layla", "variant": "zp", "zoom": "track",
     "zoom_size": 380, "model": "lipsync-2-pro", "options": {"temperature": 0.8}, "use": False, "asd": "auto"},
]
CUTS = [15, 33, 49, 66, 128, 160, 212, 781, 850, 921, 963, 1028, 1085, 1111, 1150, 1198, 1221, 1255, 1280, 1330, 1363,
        1425, 1471, 1513, 1641, 1707, 1752]


def load(p, ch=2):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", str(ch), "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    return (x.reshape(-1, ch) if ch > 1 else x).copy()


def save(p, x):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a",
                    "pcm_s24le", p], input=x.astype(np.float32).tobytes(), check=True)


def lufs(x):
    """Integrated loudness (EBU R128) of a mono signal."""
    out = subprocess.run(["ffmpeg", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-af", "ebur128",
                          "-f", "null", "-"], input=x.astype(np.float32).tobytes(), capture_output=True).stderr.decode()
    v = [ln for ln in out.split("Summary")[-1].splitlines() if ln.strip().startswith("I:")]
    return float(v[0].split()[1]) if v else float("nan")


def median_f0(x):
    import parselmouth
    from parselmouth.praat import call
    p = call(parselmouth.Sound(x.astype(np.float64), SR), "To Pitch", 0.0, 120, 600)
    return call(p, "Get quantile", 0, 0, 0.5, "Hertz")


def window(n, a, b, fade=0.02):
    t = np.arange(n) / SR
    w = np.clip((t - (a - fade / 2)) / fade, 0, 1) * np.clip(((b + fade / 2) - t) / fade, 0, 1)
    return 0.5 - 0.5 * np.cos(np.pi * w)


def speech_parts(x, floor=35.0):
    """Energy envelope (10 ms) -> (start, end) of the speech, and the pauses inside it (start, length), in samples."""
    w = int(0.01 * SR)
    db = np.array([20 * np.log10(np.sqrt(np.mean(x[i:i + w] ** 2)) + 1e-9) for i in range(0, len(x) - w, w)])
    on = db > db.max() - floor
    idx = np.flatnonzero(on)
    a, b = idx[0], idx[-1] + 1
    pauses, k = [], a
    while k < b:
        if not on[k]:
            j = k
            while j < b and not on[j]:
                j += 1
            pauses.append((k * w, (j - k) * w))
            k = j
        else:
            k += 1
    return a * w, b * w, pauses


def take_audio(w, spec):
    """A take, trimmed to its speech. 'take:i' = the i-th phrase of a take split at its longest pause."""
    name, part = (spec.split(":") + [None])[:2]
    x = load(os.path.join(w, "tts", f"{name}.mp3"), 1)
    a, b, pauses = speech_parts(x)
    if part is not None:
        p0, pl = max(pauses, key=lambda p: p[1])  # split at the longest pause inside the take
        a, b = (a, p0) if part == "0" else (p0 + pl, b)
        _, _, pauses = speech_parts(x[a:b])
        pauses = [(p + a, l) for p, l in pauses]
    m = int(0.03 * SR)  # keep 30 ms around the speech
    a, b = max(0, a - m), min(len(x), b + m)
    y = x[a:b].copy()
    # shorten long pauses inside the line
    xf = int(0.015 * SR)
    for p0, pl in sorted(pauses, reverse=True):
        if pl / SR > MAX_PAUSE:
            cut = pl - int(MAX_PAUSE * SR)
            s = p0 - a + (pl - cut) // 2
            if 0 < s - xf and s + cut + xf < len(y):
                r = np.linspace(1, 0, xf)
                y[s - xf:s] = y[s - xf:s] * r + y[s + cut - xf:s + cut] * (1 - r)
                y = np.concatenate([y[:s], y[s + cut:]])
    return y


def main():
    w, ex = sys.argv[1], sys.argv[2]
    vocals = load(os.path.join(w, "stems", "fragmento_vocals.wav"))
    bg = load(os.path.join(w, "stems", "fragmento_bg.wav"))
    n = len(vocals)
    orig_mono = vocals.mean(1)
    track = np.zeros(n, np.float32)
    placed = {}
    ref_f0 = {}
    for who in ("Melody", "Layla"):
        sp = os.path.join(w, "tts", f"{who.lower()}_voice_sample.wav")
        if not os.path.exists(sp):  # Melody's clone was made for the earlier French ending
            sp = os.path.join(w, "song", f"{who.lower()}_voice_sample.wav")
        sm = load(sp, 1)
        ref_f0[who] = median_f0(sm)
    prev_end = 0.0
    for lid, who, spec, anchor, oend in LINES:
        oa, ob = anchor, oend
        y = take_audio(w, spec)
        if lid in CUT:  # interrupted line: stop it there, with a short fade
            y = y[:int(CUT[lid] * SR)].copy()
            fo = int(0.05 * SR)
            y[-fo:] *= np.linspace(1, 0, fo)
        # speaking pitch close to the actress's own in this very line (her acting); only a clear offset is
        # corrected, and only partly
        f_t = median_f0(y)
        f_r = median_f0(orig_mono[int(oa * SR):int(ob * SR)])
        if not (f_r and f_r == f_r):
            f_r = ref_f0[who]
        st = 12 * np.log2(f_r / f_t) if f_t and f_r and f_t == f_t else 0.0
        if abs(st) > 1.5:  # 60 % of the offset, at most 2.5 semitones (PSOLA stays clean in that range)
            y = pitch_shift(y, 2 ** (float(np.clip(0.6 * st, -2.5, 2.5)) / 12))
        lim = OVERLAP_OK if lid == "L11" else -GAP
        t0 = max(anchor, prev_end - lim)
        fit = float(np.clip((oend - t0) / (len(y) / SR), *FIT)) if oend > t0 else FIT[0]
        if abs(fit - 1) > 0.005:
            y = stretch(y, int(len(y) * fit))
        # loudness of the original line (the ending is boosted: it is whispered-soft in the original)
        # (measured over at least 0.6 s: the loudness meter needs 0.4 s blocks)
        target = lufs(orig_mono[int((oa - 0.1) * SR):int(max(ob, oa + 0.6) * SR)]) + \
            (END_BOOST_DB if lid.startswith("L15") else 0)
        g = 10 ** ((target - lufs(y)) / 20)
        y = y * g
        f = int(0.008 * SR)
        y[:f] *= np.linspace(0, 1, f)
        y[-f:] *= np.linspace(1, 0, f)
        k = int(round(t0 * SR))
        track[k:k + len(y)] += y[:n - k]
        prev_end = t0 + len(y) / SR
        placed[lid] = (who, t0, prev_end, (oa, ob))
        print(f"{lid:5s} {who:6s} {t0:6.2f}-{prev_end:6.2f} (her line {oa:.2f}-{ob:.2f}, fit {fit:.2f}, pitch {st:+.1f} st"
              f"{' corrected' if abs(st) > 1.5 else ''}, gain {20 * np.log10(g):+.1f} dB)")
    dub = np.stack([track, track], 1)
    keep_orig = np.ones(n, np.float32)
    for _, a, b in SEGMENTS:
        keep_orig -= window(n, a, b, 0.03)
    keep_orig = np.clip(keep_orig, 0, 1)
    voice = vocals * keep_orig[:, None] + dub
    save(os.path.join(ex, "en", f"{CLIP}_EN.wav"), dub)
    save(os.path.join(w, "enhe", "voice_final.wav"), voice)
    mix = voice + bg
    print(f"final mix peak {20 * np.log10(np.abs(mix).max()):.1f} dBFS")
    save(os.path.join(w, "enhe", "final_mix.wav"), mix)
    jobs = []
    for j in JOBS:
        lines = [(lid, v) for lid, v in placed.items() if v[0] == j["who"]
                 and v[1] < (j["last"] + 1) / (24000 / 1001) and v[2] > j["first"] / (24000 / 1001)]
        keep = [[round(v[1] - 0.05, 2), round(v[2] + 0.05, 2)] for _, v in lines]
        also = [[round(v[3][0] - 0.08, 2), round(v[3][1] + 0.08, 2)] for _, v in lines]
        f_a, f_b = j["first"] / (24000 / 1001), (j["last"] + 1) / (24000 / 1001)
        # the original mouth also moved where this speaker had lines that now fall outside this shot
        for lid, who, spec, oa, ob in LINES:
            if who == j["who"] and ob > f_a and oa < f_b and not any(l == lid for l, _ in lines):
                also.append([round(oa - 0.08, 2), round(ob + 0.08, 2)])
        jobs.append({"first": j["first"], "last": j["last"], "face": j["face"], "en_keep": keep or [[f_a, f_a + 0.1]],
                     "mask": "mouth", "also_windows": also, "note": j["who"],
                     **{key: j[key] for key in ("steady", "variant", "zoom", "zoom_size", "options", "use", "asd", "model",
                                          "fade_profile")
                        if key in j}})
    plan = {CLIP: {"assemble": "masked", "cuts": CUTS, "jobs": jobs,
                   "note": "Melody EP101 demo v2: Spanish original, English (native accent), Hebrew (lip-synced)"}}
    os.makedirs(os.path.join(ex, "analysis"), exist_ok=True)
    json.dump(plan, open(os.path.join(ex, "plan.json"), "w"), indent=1)
    json.dump([{"clip": CLIP, "frames": 2013}], open(os.path.join(ex, "clips.json"), "w"), indent=1)
    for p, v in ((os.path.join(ex, "transcripts.json"), {}), (os.path.join(ex, "analysis", "analysis.json"), [])):
        if not os.path.exists(p):
            json.dump(v, open(p, "w"))
    print("plan:", len(jobs), "jobs")


if __name__ == "__main__":
    main()
