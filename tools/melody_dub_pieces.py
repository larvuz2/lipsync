"""Dub chosen stretches of the Melody dialogue stem with Sync (ElevenLabs Dubbing v2), as one source.

    python3 tools/melody_dub_pieces.py work/melody <name> <target_lang> <cloning_strength> <a-b>[,<a-b>...]

The stretches (clip seconds) are joined with 1 s of silence, so the engine clones each voice from all of them.
Lower cloning strength = more native accent in the target language (the voice stays close, the accent follows
the target language). Writes work/melody/dub/<name>_<lang>_s<strength>.flac and <name>_map.json.
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


def main():
    w, name, lang, strength = Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
    pieces = [tuple(float(v) for v in p.split("-")) for p in sys.argv[5].split(",")]
    d = w / "dub"
    src = d / f"{name}_source.flac"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(w / "stems" / "fragmento_vocals.wav"), "-ac", "2", "-ar",
                          str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    v = np.frombuffer(raw, np.float32).reshape(-1, 2)
    parts, mp, t = [], [], 0.0
    for a, b in pieces:
        parts += [v[int(a * SR):int(b * SR)], np.zeros((SR, 2), np.float32)]
        mp.append({"clip_start": a, "clip_end": b, "src_start": t})
        t += (b - a) + 1.0
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "flac",
                    str(src)], input=np.concatenate(parts[:-1]).astype(np.float32).tobytes(), check=True)
    json.dump(mp, open(d / f"{name}_map.json", "w"), indent=1)
    asset = api.upload(src, name=f"Melody EP101 {name} (dub source)", project_id=PROJECT)
    job = api.dub_audio(asset["id"], target=lang, source="es", strength=strength, project_id=PROJECT,
                        idempotency_key=f"melody-{name}-{asset['id']}-{lang}-{strength}")
    out = d / f"{name}_{lang}_s{strength}.flac"
    if job["status"] == "COMPLETED":
        api.download(job["outputMediaUrl"], out)
    print(name, lang, strength, job["status"], job.get("error") or "", out.name if out.exists() else "")


if __name__ == "__main__":
    main()
