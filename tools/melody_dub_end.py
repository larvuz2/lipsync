"""Melody EP101 demo: French dub of the spoken ending ("Mi futuro… mi futuro es hoy", after her humming).

    python3 tools/melody_dub_end.py work/melody

Same process as the other lines (Sync, ElevenLabs Dubbing v2, fr-FR). The source is Melody's dialogue stem:
her lines 12-14 (61.0-67.6 s, so the voice clone and the wording match the French line 14 that plays just before)
and the ending (80.40-83.60 s, after the humming), joined with 1 s of silence. Only the ending is used.
Writes work/melody/dub/end_fr-FR.flac (the dub) and end_map.json.
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
PIECES = [(61.00, 67.60), (80.40, 83.60)]


def main():
    w = Path(sys.argv[1])
    d = w / "dub"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(w / "stems" / "fragmento_vocals.wav"), "-ac", "2", "-ar",
                          str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    v = np.frombuffer(raw, np.float32).reshape(-1, 2)
    parts, mp, t = [], [], 0.0
    for a, b in PIECES:
        parts += [v[int(a * SR):int(b * SR)], np.zeros((SR, 2), np.float32)]
        mp.append({"clip_start": a, "clip_end": b, "src_start": t})
        t += (b - a) + 1.0
    src = d / "end_source.flac"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "flac",
                    str(src)], input=np.concatenate(parts[:-1]).astype(np.float32).tobytes(), check=True)
    json.dump(mp, open(d / "end_map.json", "w"), indent=1)
    asset = api.upload(src, name="Melody EP101 ending (dub source)", project_id=PROJECT)
    job = api.dub_audio(asset["id"], target="fr-FR", source="es", strength=8, project_id=PROJECT,
                        idempotency_key=f"melody-end-{asset['id']}-fr")
    print(job["status"], job.get("error"))
    if job["status"] == "COMPLETED":
        api.download(job["outputMediaUrl"], d / "end_fr-FR.flac")
        print("wrote", d / "end_fr-FR.flac")


if __name__ == "__main__":
    main()
