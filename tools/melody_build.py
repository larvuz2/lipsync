"""Melody EP101 multi-language demo: build the voice tracks and the lip-sync plan.

    python3 tools/melody_build.py work/melody exchange/melody

Language plan (clip seconds): Spanish original until 16.50, English 16.50-29.60 (lines 3-7), Hebrew 53.40-60.16
(lines 8-10), Portuguese 60.16-66.18 (lines 11-13), French 66.18-67.80 (line 14) and the sung line (song_fr.wav,
made by melody_song.py, 80.9-83.3). Each cut sits in a pause of both neighbouring dubs.
Writes:
  exchange/melody/en/00000101_EN.wav   dubbed voices only (job audio for lip sync)
  work/melody/mix/voice_final.wav      dialogue stem of the demo (original Spanish + dubs + French song)
  work/melody/mix/final_mix.wav        voice_final + music/effects stem
  exchange/melody/plan.json, clips.json, transcripts.json, analysis/analysis.json
"""
import json
import os
import subprocess
import sys

import numpy as np

SR = 48000
FPS = 24000 / 1001
CLIP = "00000101"
SEGMENTS = [("en-US", 16.50, 29.60), ("he", 53.40, 60.16), ("pt-BR", 60.16, 66.18), ("fr-FR", 66.18, 67.80)]
# per line: language, speaker, window (clip s), gain dB (matches the original line's loudness, capped)
LINES = [
    ("L3", "en-US", "Layla", 16.74, 18.35, 1.2), ("L4", "en-US", "Melody", 18.54, 20.43, 1.3),
    ("L5", "en-US", "Melody", 21.34, 23.71, 3.0), ("L6", "en-US", "Layla", 24.38, 26.80, 0.2),
    ("L7", "en-US", "Layla", 26.80, 29.00, 1.9),
    ("L8", "he", "Melody", 53.69, 54.66, -3.0), ("L9", "he", "Layla", 56.42, 58.84, 1.1),
    ("L10", "he", "Layla", 58.84, 60.16, 3.0),
    ("L11", "pt-BR", "Melody", 60.17, 61.02, 2.1), ("L12", "pt-BR", "Melody", 61.02, 63.87, 1.8),
    ("L13", "pt-BR", "Melody", 63.87, 66.18, 0.0),
    ("L14", "fr-FR", "Melody", 66.18, 67.74, 0.9),
]
# where the ORIGINAL Spanish lines move the mouth (Whisper segments): lip-synced mouth also covers these
ORIG = {"L3": (16.84, 18.04), "L4": (18.68, 20.18), "L5": (21.49, 23.29), "L6": (24.48, 26.52), "L7": (26.84, 28.90),
        "L8": (53.85, 54.37), "L9": (56.87, 58.61), "L10": (58.83, 59.59), "L11": (59.59, 60.29),
        "L12": (61.11, 63.51), "L13": (63.85, 66.33), "L14": (66.33, 67.27), "song": (81.00, 83.12)}
SONG = (80.90, 83.30)
# final-mix trim per language (dB), so each dubbed section has the original voice's loudness (EBU R128, K-weighted;
# the dubbed voices are brighter, so plain RMS matching left them about 3 dB loud). Not applied to the lip-sync audio.
TRIM = {"en-US": -2.8, "he": -3.3, "pt-BR": -2.8, "fr-FR": -1.8, "song": -2.4}  # French sung line replaces the original vocal here
# lip-sync jobs: frames, face pin (frame, x, y), speaker, gate windows from LINES
JOBS = [
    {"first": 393, "last": 714, "face": [457, 519, 361], "who": "Melody", "langs": ["en-US"]},
    {"first": 393, "last": 714, "face": [600, 1373, 153], "who": "Layla", "langs": ["en-US"]},
    {"first": 1281, "last": 1329, "face": [1300, 874, 234], "who": "Melody", "langs": ["he"]},
    {"first": 1363, "last": 1424, "face": [1394, 1563, 428], "who": "Layla", "langs": ["he"]},
    {"first": 1425, "last": 1470, "face": [1448, 763, 408], "who": "Melody", "langs": ["pt-BR"]},
    {"first": 1513, "last": 1640, "face": [1577, 761, 410], "who": "Melody", "langs": ["pt-BR", "fr-FR"]},
    {"first": 1925, "last": 2012, "face": [1944, 902, 462], "who": "Melody", "langs": ["song"],
     "keep": [[80.98, 81.85], [82.36, 83.20]]},  # the French sung line (close-up at the mic)
]


def load(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def save(p, x, fmt="pcm_s24le"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", fmt, p],
                   input=x.astype(np.float32).tobytes(), check=True)


def window(n, a, b, fade=0.02):
    """0..1 envelope: 1 inside [a, b], raised-cosine fades of `fade` s centred on the edges."""
    t = np.arange(n) / SR
    w = np.clip((t - (a - fade / 2)) / fade, 0, 1) * np.clip(((b + fade / 2) - t) / fade, 0, 1)
    return 0.5 - 0.5 * np.cos(np.pi * w)


def main():
    w, ex = sys.argv[1], sys.argv[2]
    vocals = load(os.path.join(w, "stems", "fragmento_vocals.wav"))
    bg = load(os.path.join(w, "stems", "fragmento_bg.wav"))
    n = len(vocals)
    mp = json.load(open(os.path.join(w, "dub", "map.json")))
    dubs = {}
    for lang, _, _ in SEGMENTS:
        x = load(os.path.join(w, "dub", f"dub_{lang}.flac"))
        tr = np.zeros((n, 2), np.float32)
        for p in mp:  # the dub source was two dialogue scenes joined: put each piece back at its clip time
            L = int(round((p["clip_end"] - p["clip_start"]) * SR))
            s, c = int(round(p["src_start"] * SR)), int(round(p["clip_start"] * SR))
            seg = x[s:s + L]
            tr[c:c + len(seg)] = seg
        if lang == "pt-BR" and os.path.exists(os.path.join(w, "dub", "l11_pt.wav")):
            # line 11 as its own take (melody_l11.py): in the dub, "Não" ran into Layla's line and got clipped
            l11 = load(os.path.join(w, "dub", "l11_pt.wav"))
            a, b = int(60.12 * SR), int(61.03 * SR)
            tr[a:b] = 0
            k = int(60.17 * SR)
            tr[k:k + len(l11)] += l11
        dubs[lang] = tr
    # line gains, as a smooth per-language gain curve
    gain = {lang: np.ones(n, np.float32) for lang, _, _ in SEGMENTS}
    for _, lang, _, a, b, g in LINES:
        e = window(n, a, b, 0.04)
        gain[lang] = gain[lang] * (1 - e) + e * (10 ** (g / 20))
    dub_only = np.zeros((n, 2), np.float32)
    dub_mix = np.zeros((n, 2), np.float32)
    keep_orig = np.ones(n, np.float32)
    for lang, a, b in SEGMENTS:
        e = window(n, a, b, 0.02)
        dub_only += dubs[lang] * (gain[lang] * e)[:, None]
        dub_mix += dubs[lang] * (gain[lang] * e * 10 ** (TRIM[lang] / 20))[:, None]
        keep_orig -= e
    keep_orig = np.clip(keep_orig, 0, 1)
    voice = vocals * keep_orig[:, None] + dub_mix
    song_p = os.path.join(w, "song", "song_fr.wav")
    if os.path.exists(song_p):
        s = load(song_p)[:n]
        e = window(n, *SONG, 0.03)
        voice = voice * (1 - e)[:, None] + np.pad(s, ((0, n - len(s)), (0, 0))) * (e * 10 ** (TRIM["song"] / 20))[:, None]
        dub_only = dub_only + np.pad(s, ((0, n - len(s)), (0, 0))) * e[:, None]
        print("French song included")
    save(os.path.join(ex, "en", f"{CLIP}_EN.wav"), dub_only)
    save(os.path.join(w, "mix", "voice_final.wav"), voice)
    mix = voice + bg
    peak = np.abs(mix).max()
    print(f"final mix peak {20 * np.log10(peak):.1f} dBFS")
    save(os.path.join(w, "mix", "final_mix.wav"), mix)
    # lip-sync plan
    jobs = []
    for j in JOBS:
        keep = j.get("keep") or [[round(a, 2), round(b, 2)] for _, lang, who, a, b, _ in LINES
                                 if who == j["who"] and lang in j["langs"]]
        also = [[round(ORIG[i][0] - 0.08, 2), round(ORIG[i][1] + 0.08, 2)] for i, lang, who, *_ in LINES
                if who == j["who"] and lang in j["langs"]]
        if "song" in j["langs"]:
            also.append([ORIG["song"][0] - 0.08, ORIG["song"][1] + 0.08])
        jobs.append({"first": j["first"], "last": j["last"], "face": j["face"], "en_keep": keep, "mask": "mouth",
                     "also_windows": also, "note": f"{j['who']} ({', '.join(j['langs'])})"})
    plan = {CLIP: {"assemble": "masked", "cuts": [15, 33, 49, 66, 128, 160, 212, 781, 850, 921, 963, 1028, 1085, 1111, 1150, 1198,
                            1221, 1255, 1280, 1330, 1363, 1425, 1471, 1513, 1641, 1707, 1752],
                   "jobs": jobs,
                   "note": "Melody EP101 demo: Spanish original, then English, Hebrew, Portuguese, French (lip-synced)"}}
    os.makedirs(os.path.join(ex, "analysis"), exist_ok=True)
    json.dump(plan, open(os.path.join(ex, "plan.json"), "w"), indent=1)
    json.dump([{"clip": CLIP, "frames": 2013}], open(os.path.join(ex, "clips.json"), "w"), indent=1)
    if not os.path.exists(os.path.join(ex, "transcripts.json")):
        json.dump({}, open(os.path.join(ex, "transcripts.json"), "w"))
    if not os.path.exists(os.path.join(ex, "analysis", "analysis.json")):
        json.dump([], open(os.path.join(ex, "analysis", "analysis.json"), "w"))
    print("plan:", len(jobs), "jobs")


if __name__ == "__main__":
    main()
