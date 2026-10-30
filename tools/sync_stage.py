"""Run the sync.so API parts of a dubbing test. Needs SYNC_API_KEY in the environment.

Stage 1: clone voices, synthesize every English line variant, run Sync's auto-dub for comparison.
    python3 tools/sync_stage.py stage1 data/test1_lines.json exchange/test1

Stage 2: lip-sync jobs listed in <exchange>/lipsync_jobs.json.
    python3 tools/sync_stage.py stage2 exchange/test1

Everything downloaded lands under <exchange>/stage1 or <exchange>/stage2 with a manifest JSON.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_api as api  # noqa: E402

MEDIA = Path(__file__).resolve().parent.parent / "media" / "LIP SYNC TEST"


def clip_file(clip: str) -> Path:
    hits = glob.glob(str(MEDIA / f"*{clip}.mp4"))
    if not hits:
        sys.exit(f"Missing media for {clip}. Run: python3 tools/fetch_drive.py")
    return Path(hits[0])


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))


# ---------------------------------------------------------------- stage 1

def get_or_clone_voice(name: str, sample: Path) -> dict:
    for v in api.list_voices():
        if v.get("name") == name:
            print(f"reusing voice '{name}'")
            return {"voiceId": v.get("voiceId") or v.get("id"), "syncId": v.get("internalVoiceId") or v.get("id"),
                    "name": name, "reused": True}
    asset = api.upload(sample, name=f"{name} sample")
    v = api.clone_voice(name, asset_id=asset["id"])
    print(f"cloned voice '{name}' -> {v['voiceId']}")
    return {"voiceId": v["voiceId"], "syncId": v["id"], "name": name, "assetId": asset["id"], "reused": False}


def stage1(sheet_path: str, exch: str) -> None:
    sheet = json.loads(Path(sheet_path).read_text())
    ex = Path(exch)
    out = ex / "stage1"
    inputs = ex / "inputs"
    manifest: dict = {"voices": {}, "tts": [], "autodub": None}
    prev = out / "manifest.json"
    done_tts = {}
    if prev.exists():  # rerun: keep takes already downloaded instead of paying for them again
        done_tts = {t["name"]: t for t in json.loads(prev.read_text()).get("tts", []) if (ex / t["file"]).exists()}

    for spk, cfg in sheet["speaker_voices"].items():
        manifest["voices"][spk] = get_or_clone_voice(cfg["clone_name"], inputs / f"voice_sample_{spk}.wav")
    save_json(out / "manifest.json", manifest)

    # TTS: every variant, two takes (more expressive / steadier).
    takes = [{"stability": 0.35, "similarity": 0.9}, {"stability": 0.6, "similarity": 0.9}]
    for clip, c in sheet["clips"].items():
        for line in c["lines"]:
            voice = manifest["voices"][line["speaker"]]["voiceId"]
            for vi, var in enumerate(line["variants"]):
                for ti, tk in enumerate(takes):
                    name = f"{line['id']}_v{vi}_t{ti}"
                    if name in done_tts:
                        manifest["tts"].append(done_tts[name]); continue
                    for attempt in range(4):
                        try:
                            r = api.tts(var["tts"], voice, stability=tk["stability"], similarity=tk["similarity"])
                            break
                        except RuntimeError as e:  # 429 or transient
                            print(f"{name}: {e}; retrying"); time.sleep(5 * (attempt + 1))
                    else:
                        continue
                    dest = api.download(r["url"], out / "tts" / f"{name}{Path(r['url'].split('?')[0]).suffix or '.mp3'}")
                    manifest["tts"].append({"name": name, "line": line["id"], "variant": vi, "take": ti, **tk,
                                            "text": var["tts"], "duration": r.get("duration"), "file": str(dest.relative_to(ex)),
                                            "url": r["url"]})
                    print(f"tts {name}: {r.get('duration')} s")
    save_json(out / "manifest.json", manifest)

    # Sync / ElevenLabs auto-dub of the joined scene, for comparison (Test A).
    # Fixed project id so reruns reuse the same project.
    proj = api.create_project("Raven test1 autodub", project_id="5f1d2c3a-7b4e-4c1a-9e2d-0a7b3c6d8e11")
    asset = api.upload(inputs / "autodub_source.wav", name="Raven test1 autodub source", project_id=proj["id"])
    job = api.dub_audio(asset["id"], target="en-US", source="hu", strength=7, project_id=proj["id"])
    entry = {"jobId": job["id"], "projectId": proj["id"], "status": job["status"], "error": job.get("error"),
             "outputDurationSec": job.get("outputDurationSec")}
    if job["status"] == "COMPLETED" and job.get("outputMediaUrl"):
        u = job["outputMediaUrl"]
        dest = api.download(u, out / f"autodub_en{Path(u.split('?')[0]).suffix or '.mp3'}")
        entry.update({"file": str(dest.relative_to(ex)), "url": u})
    manifest["autodub"] = entry
    print("autodub:", entry["status"], entry.get("error") or "")
    save_json(out / "manifest.json", manifest)


# ---------------------------------------------------------------- stage 2

def trim_video(clip: str, first: int, last: int, dest: Path) -> Path:
    """Frame-exact cut of the clip's picture (no audio), high-quality H.264."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip_file(clip)),
                    "-vf", f"select='between(n,{first},{last})',setpts=N/FRAME_RATE/TB",
                    "-an", "-r", "24000/1001", "-c:v", "libx264", "-crf", "10", "-preset", "slow",
                    "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    str(dest)], check=True)
    return dest


def run_job(job: dict, ex: Path, cache: dict) -> dict:
    clip = job["clip"]
    key = (clip, job["first_frame"], job["last_frame"])
    if key not in cache:
        v = trim_video(clip, job["first_frame"], job["last_frame"], ex / "stage2" / "src" / f"{clip}_f{key[1]}-{key[2]}.mp4")
        cache[key] = api.upload(v, name=v.name)["id"]
    audio = api.upload(ex / job["audio"], name=Path(job["audio"]).name)["id"]
    body = {"model": job["model"],
            "input": [{"type": "video", "assetId": cache[key]}, {"type": "audio", "assetId": audio}],
            "options": {"sync_mode": "cut_off"},
            "outputFileName": job["name"]}
    if job.get("face"):
        body["options"]["active_speaker_detection"] = {"auto_detect": False, "frame_number": job["face"]["frame"],
                                                        "coordinates": job["face"]["xy"]}
    gen = api.generate(body)
    print(f"{job['name']}: submitted {gen['id']}")
    g = api.wait_generation(gen["id"])
    res = {**job, "generationId": gen["id"], "status": g["status"], "error": g.get("error"),
           "errorCode": g.get("errorCode"), "outputUrl": g.get("outputUrl"), "outputDuration": g.get("outputDuration")}
    if g["status"] == "COMPLETED" and g.get("outputUrl"):
        res["file"] = str(api.download(g["outputUrl"], ex / "stage2" / "out" / f"{job['name']}.mp4").relative_to(ex))
    print(f"{job['name']}: {g['status']} {g.get('error') or ''}")
    return res


def stage2(exch: str) -> None:
    ex = Path(exch)
    jobs = json.loads((ex / "lipsync_jobs.json").read_text())
    prev = ex / "stage2" / "manifest.json"
    done = {}
    if prev.exists():  # rerun: keep finished jobs instead of paying for them again
        done = {r["name"]: r for r in json.loads(prev.read_text())
                if r.get("status") == "COMPLETED" and r.get("file") and (ex / r["file"]).exists()}
    todo = [j for j in jobs if j["name"] not in done]
    cache: dict = {}
    # Upload the trimmed videos first (sequentially) so parallel jobs share them.
    for j in todo:
        key = (j["clip"], j["first_frame"], j["last_frame"])
        if key not in cache:
            v = trim_video(j["clip"], *key[1:], ex / "stage2" / "src" / f"{key[0]}_f{key[1]}-{key[2]}.mp4")
            cache[key] = api.upload(v, name=v.name)["id"]
    with ThreadPoolExecutor(max_workers=3) as pool:  # Creator plan: 3 concurrent jobs
        results = list(pool.map(lambda j: safe_job(j, ex, cache), todo))
    by_name = {**done, **{r["name"]: r for r in results}}
    save_json(ex / "stage2" / "manifest.json", [by_name[j["name"]] for j in jobs if j["name"] in by_name])


def safe_job(job: dict, ex: Path, cache: dict) -> dict:
    try:
        return run_job(job, ex, cache)
    except Exception as e:  # keep the other jobs' results
        print(f"{job['name']}: ERROR {e}")
        return {**job, "status": "ERROR", "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "stage1":
        stage1(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 2 and sys.argv[1] == "stage2":
        stage2(sys.argv[2])
    else:
        print(__doc__)
