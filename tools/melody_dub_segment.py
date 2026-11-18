"""Dub one stretch of the Melody dialogue/vocal stem with Sync (ElevenLabs Dubbing v2).

    python3 tools/melody_dub_segment.py work/melody <name> <start> <end> <target_lang> [strength]

Writes work/melody/dub/seg_<name>_<lang>.flac (same length/timing as the source stretch).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_api as api  # noqa: E402

PROJECT = "7d1e5a3c-2b4f-4e8a-9c6d-1f0e2a3b4c5d"


def main():
    w, name, a, b, lang = Path(sys.argv[1]), sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    strength = int(sys.argv[6]) if len(sys.argv) > 6 else 8
    d = w / "dub"
    src = d / f"seg_{name}_src.flac"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i",
                    str(w / "stems" / "fragmento_vocals.wav"), "-c:a", "flac", str(src)], check=True)
    asset = api.upload(src, name=f"Melody EP101 {name} source", project_id=PROJECT)
    job = api.dub_audio(asset["id"], target=lang, source="es", strength=strength, project_id=PROJECT,
                        idempotency_key=f"melody-{name}-{asset['id']}-{lang}-{strength}")
    rec = {"name": name, "start": a, "end": b, "lang": lang, "strength": strength, "jobId": job["id"],
           "status": job["status"], "error": job.get("error")}
    if job["status"] == "COMPLETED" and job.get("outputMediaUrl"):
        dest = api.download(job["outputMediaUrl"], d / f"seg_{name}_{lang}.flac")
        rec["file"] = dest.name
    man_p = d / "segments.json"
    man = json.load(open(man_p)) if man_p.exists() else []
    man.append(rec)
    json.dump(man, open(man_p, "w"), indent=1)
    print(rec)


if __name__ == "__main__":
    main()
