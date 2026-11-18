"""Melody EP101 demo: dub the dialogue into English, Hebrew, Portuguese and French (ElevenLabs Dubbing v2 via Sync).

    python3 tools/melody_dub.py work/melody

Source = the Demucs dialogue stem, only the two dialogue scenes (8.40-29.40 s and 53.40-67.80 s) joined with 1 s of
silence, so the dubbing engine clones each girl's voice from all of her lines. Writes work/melody/dub/dub_<lang>.*
and dub/map.json (where each piece of the source sits in the clip).
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_api as api  # noqa: E402

SR = 48000
PIECES = [(8.40, 29.40), (53.40, 67.80)]
GAP = 1.0
TARGETS = ["en-US", "he", "pt-BR", "fr-FR"]


def load(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)


def main():
    w = Path(sys.argv[1])
    d = w / "dub"
    d.mkdir(parents=True, exist_ok=True)
    src = d / "dub_source.flac"
    if not src.exists():
        v = load(str(w / "stems" / "fragmento_vocals.wav"))
        parts, mp, t = [], [], 0.0
        for a, b in PIECES:
            seg = v[int(a * SR):int(b * SR)]
            parts += [seg, np.zeros((int(GAP * SR), 2), np.float32)]
            mp.append({"clip_start": a, "clip_end": b, "src_start": t})
            t += (b - a) + GAP
        x = np.concatenate(parts[:-1])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-c:a", "flac", str(src)], input=x.astype(np.float32).tobytes(), check=True)
        json.dump(mp, open(d / "map.json", "w"), indent=1)
    proj = api.create_project("Melody EP101 demo dub", project_id="7d1e5a3c-2b4f-4e8a-9c6d-1f0e2a3b4c5d")
    asset = api.upload(src, name="Melody EP101 dialogue (dub source)", project_id=proj["id"])
    man_p = d / "manifest.json"
    man = json.load(open(man_p)) if man_p.exists() else {}
    lock = threading.Lock()

    def run(lang):
        if man.get(lang, {}).get("status") == "COMPLETED":
            return
        job = api.dub_audio(asset["id"], target=lang, source="es", strength=8, project_id=proj["id"],
                            idempotency_key=f"melody-ep101-{asset['id']}-{lang}")
        rec = {"jobId": job["id"], "status": job["status"], "error": job.get("error"),
               "seconds": job.get("outputDurationSec")}
        if job["status"] == "COMPLETED" and job.get("outputMediaUrl"):
            u = job["outputMediaUrl"]
            dest = api.download(u, d / f"dub_{lang}{Path(u.split('?')[0]).suffix or '.flac'}")
            rec["file"] = dest.name
        with lock:
            man[lang] = rec
            json.dump(man, open(man_p, "w"), indent=1)
        print(lang, rec, flush=True)

    ts = [threading.Thread(target=run, args=(lg,)) for lg in TARGETS]
    [t.start() for t in ts]
    [t.join() for t in ts]


if __name__ == "__main__":
    main()
