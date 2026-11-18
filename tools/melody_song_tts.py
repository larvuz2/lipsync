"""Melody EP101 demo: clone Melody's voice (Sync / ElevenLabs IVC) from her clean Spanish lines and voice the French
lyric takes for the sung line.

    python3 tools/melody_song_tts.py work/melody
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
MELODY_LINES = [(12.85, 16.30), (18.60, 20.30), (21.40, 23.40), (61.05, 63.60), (63.80, 66.40)]
TEXTS = {"a": "Mon avenir... c'est aujourd'hui.", "b": "Mon a-ve-nir... C'est au-jour-d'hui !"}
SETTINGS = [(0.3, 0.9), (0.45, 0.9), (0.6, 0.85)]


def main():
    w = Path(sys.argv[1]) / "song"
    w.mkdir(parents=True, exist_ok=True)
    man_p = w / "tts_manifest.json"
    man = json.load(open(man_p)) if man_p.exists() else {"takes": []}
    if "voiceId" not in man:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(w.parent / "stems" / "fragmento_vocals.wav"), "-ac", "1",
                              "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(raw, np.float32)
        parts = []
        for a, b in MELODY_LINES:
            parts += [x[int(a * SR):int(b * SR)], np.zeros(int(0.4 * SR), np.float32)]
        s = np.concatenate(parts)
        sample = w / "melody_voice_sample.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-c:a", "pcm_s16le", str(sample)], input=s.tobytes(), check=True)
        asset = api.upload(sample, name="Melody EP101 - Melody voice sample", project_id=PROJECT)
        v = api.clone_voice("Melody EP101 demo - Melody", asset_id=asset["id"])
        man.update({"voiceId": v["voiceId"], "syncId": v["id"]})
        json.dump(man, open(man_p, "w"), indent=1)
        print("voice", v["voiceId"], flush=True)
    for key, text in TEXTS.items():
        for k, (st, sim) in enumerate(SETTINGS):
            dest = w / f"tts_{key}{k}.mp3"
            if dest.exists():
                continue
            r = api.tts(text, man["voiceId"], stability=st, similarity=sim)
            api.download(r["url"], dest)
            man["takes"].append({"file": dest.name, "text": text, "stability": st, "similarity": sim,
                                 "duration": r.get("duration")})
            json.dump(man, open(man_p, "w"), indent=1)
            print("take", dest.name, r.get("duration"), flush=True)


if __name__ == "__main__":
    main()
