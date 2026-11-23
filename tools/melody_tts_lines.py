"""Melody EP101 EN/HE version: voice the approved script line by line in each girl's cloned voice (Sync TTS,
ElevenLabs), several takes per line.

    python3 tools/melody_tts_lines.py work/melody [line_id ...]

Voices: Sync/ElevenLabs instant clones from each girl's own clean Spanish lines (dialogue stem). Takes are written
to work/melody/tts/<id>_t<k>.mp3 with tts/manifest.json; reruns skip finished takes and reuse the clones.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_api as api  # noqa: E402

SR = 48000
PROJECT = "7d1e5a3c-2b4f-4e8a-9c6d-1f0e2a3b4c5d"
SAMPLES = {"Melody": [(12.85, 16.30), (18.60, 20.30), (21.40, 23.40), (61.05, 63.60), (63.80, 66.40)],
           "Layla": [(16.80, 18.10), (24.40, 26.60), (26.80, 29.00), (56.80, 58.70), (58.80, 59.50)]}
LINES = [
    ("L3", "Layla", "en", "How much longer?"),
    ("L4", "Melody", "en", "I know, don't even say it."),
    ("L5", "Melody", "en", "What about Charlie? Everything okay?"),
    ("L6", "Layla", "en", "With him, everything's always more than fine."),
    ("L7", "Layla", "en", "Charlie is the picture of balance."),
    ("L8", "Melody", "he", "מוכנה."),
    ("L9", "Layla", "he", "כמה זה מעצבן אותי שאת צריכה להסתתר!"),
    ("L10", "Layla", "he", "תבטיחי לי שיום אחד..."),
    ("L11", "Melody", "he", "אל תגידי לי כלום."),
    ("L12", "Melody", "he", "זה העתיד, והעתיד לא קיים."),
    ("L13", "Melody", "he", "ההווה שלי זה מה שאני חיה כאן ועכשיו, כי..."),
    ("L14", "Melody", "he", "העתיד שלי הוא היום."),
    ("L15", "Melody", "he", "העתיד שלי? העתיד שלי הוא היום."),
]
SETTINGS = [(0.30, 0.85), (0.45, 0.85), (0.60, 0.80)]
SETTINGS_EN = SETTINGS + [(0.35, 0.95), (0.50, 0.95), (0.25, 0.70)]  # more takes: pick the most native accent


def main():
    w = Path(sys.argv[1])
    only = set(sys.argv[2:])
    d = w / "tts"
    d.mkdir(parents=True, exist_ok=True)
    man_p = d / "manifest.json"
    man = json.load(open(man_p)) if man_p.exists() else {"voices": {}, "takes": []}
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(w / "stems" / "fragmento_vocals.wav"), "-ac", "1", "-ar",
                          str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    song = w / "song" / "tts_manifest.json"  # Melody was cloned for the earlier French ending: reuse that voice
    if "Melody" not in man["voices"] and song.exists():
        man["voices"]["Melody"] = json.load(open(song))["voiceId"]
    for who, spans in SAMPLES.items():
        if who in man["voices"]:
            continue
        parts = []
        for a, b in spans:
            parts += [x[int(a * SR):int(b * SR)], np.zeros(int(0.4 * SR), np.float32)]
        sample = d / f"{who.lower()}_voice_sample.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-c:a", "pcm_s16le", str(sample)], input=np.concatenate(parts).tobytes(), check=True)
        asset = api.upload(sample, name=f"Melody EP101 - {who} voice sample", project_id=PROJECT)
        man["voices"][who] = api.clone_voice(f"Melody EP101 demo - {who}", asset_id=asset["id"])["voiceId"]
        json.dump(man, open(man_p, "w"), indent=1, ensure_ascii=False)
        print("voice", who, flush=True)
    have = {t["file"] for t in man["takes"]}
    for lid, who, lang, text in LINES:
        if only and lid not in only:
            continue
        for k, (st, sim) in enumerate(SETTINGS_EN if lang == "en" else SETTINGS):
            f = f"{lid}_t{k}.mp3"
            if f in have:
                continue
            r = api.tts(text, man["voices"][who], stability=st, similarity=sim)
            api.download(r["url"], d / f)
            man["takes"].append({"id": lid, "who": who, "lang": lang, "text": text, "take": k, "stability": st,
                                 "similarity": sim, "file": f})
            json.dump(man, open(man_p, "w"), indent=1, ensure_ascii=False)
            print("take", f, flush=True)


if __name__ == "__main__":
    main()
