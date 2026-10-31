"""Paid sync.so steps for the full sequence (winner recipe: Sync auto-dub + sync-3). Needs SYNC_API_KEY.

    python3 tools/full_stage.py dub     exchange/full     # one auto-dub job over all clips, in order
    python3 tools/full_stage.py lipsync exchange/full     # sync-3 jobs listed in exchange/full/lipsync_jobs.json

Clips are read from media/full/ (fetch with: python3 tools/fetch_drive.py, then see README in exchange/full).
Every clip's frame count is checked against exchange/full/clips.json before use. Reruns skip finished work.
"""
from __future__ import annotations

import glob
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_api as api  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "media" / "full"
PROJECT_ID = "7c2e9a41-3b5d-4f8e-a1c6-2d9b0e4f6a73"  # fixed, so reruns reuse the same Studio project


def load_json(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def save_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def clip_path(clip: str, expected_frames: int) -> Path:
    hits = glob.glob(str(MEDIA / f"*Splits{clip}.mp4"))
    if len(hits) != 1:
        sys.exit(f"clip {clip}: expected exactly one file in {MEDIA}, found {len(hits)}")
    n = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", hits[0]], capture_output=True, text=True).stdout)
    if n != expected_frames:
        sys.exit(f"clip {clip}: {n} frames on disk but {expected_frames} expected - stale download? Re-fetch media/full.")
    return Path(hits[0])


# ------------------------------------------------------------------ dub

def dub(exch: str) -> None:
    ex = Path(exch)
    man_p = ex / "dub" / "manifest.json"
    man = load_json(man_p, {})
    if man.get("status") == "COMPLETED" and (ex / man.get("file", "x")).exists():
        print("dub already completed:", man["file"]); return
    proj = api.create_project("Raven S01E01 full dub", project_id=PROJECT_ID)
    src = ex / "inputs" / "dub_source.flac"
    asset = api.upload(src, name="Raven S01E01 full dub source", project_id=proj["id"])
    job = api.dub_audio(asset["id"], target="en-US", source="hu", strength=7, project_id=proj["id"],
                        idempotency_key=f"raven-s01e01-full-{asset['id']}")
    man = {"jobId": job["id"], "projectId": proj["id"], "assetId": asset["id"], "status": job["status"],
           "error": job.get("error"), "outputDurationSec": job.get("outputDurationSec")}
    if job["status"] == "COMPLETED" and job.get("outputMediaUrl"):
        u = job["outputMediaUrl"]
        dest = api.download(u, ex / "dub" / f"dub_en{Path(u.split('?')[0]).suffix or '.flac'}")
        man.update({"file": str(dest.relative_to(ex)), "url": u})
    save_json(man_p, man)
    print("dub:", man["status"], man.get("error") or "", man.get("outputDurationSec"))


# ------------------------------------------------------------------ lip sync

def trim(clip: str, frames: int, first: int, last: int, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip_path(clip, frames)),
                    "-vf", f"select='between(n,{first},{last})',setpts=N/FRAME_RATE/TB",
                    "-an", "-r", "24000/1001", "-c:v", "libx264", "-crf", "10", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(dest)], check=True)
    got = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                              "stream=nb_read_frames", "-of", "csv=p=0", str(dest)], capture_output=True, text=True).stdout)
    if got != last - first + 1:
        dest.unlink()
        raise RuntimeError(f"trim {clip} {first}-{last}: got {got} frames")
    return dest


def run_job(job: dict, ex: Path, frames: dict) -> dict:
    out = ex / "lipsync" / "out" / f"{job['name']}.mp4"
    try:
        if job.get("input_from"):  # second speaker in the same shot: build on the first speaker's output
            v = ex / "lipsync" / "out" / f"{job['input_from']}.mp4"
            if not v.exists():
                raise RuntimeError(f"chain input {job['input_from']} not finished")
        else:
            v = trim(job["clip"], frames[job["clip"]], job["first_frame"], job["last_frame"],
                     ex / "lipsync" / "src" / f"{job['clip']}_f{job['first_frame']}-{job['last_frame']}.mp4")
        vid = api.upload(v, name=v.name, project_id=PROJECT_ID)["id"]
        aud = api.upload(ex / job["audio"], name=Path(job["audio"]).name, project_id=PROJECT_ID)["id"]
        body = {"model": "sync-3", "projectId": PROJECT_ID,
                "input": [{"type": "video", "assetId": vid}, {"type": "audio", "assetId": aud}],
                "options": {"sync_mode": "cut_off"}, "outputFileName": job["name"]}
        face = job.get("face")
        if face == "auto":
            body["options"]["active_speaker_detection"] = {"auto_detect": True}
        elif face:
            body["options"]["active_speaker_detection"] = {"auto_detect": False, "frame_number": face["frame"],
                                                            "coordinates": face["xy"]}
        gen = api.generate(body)
        print(f"{job['name']}: submitted {gen['id']}", flush=True)
        g = api.wait_generation(gen["id"])
        res = {**job, "generationId": gen["id"], "status": g["status"], "error": g.get("error"),
               "errorCode": g.get("errorCode"), "outputUrl": g.get("outputUrl")}
        if g["status"] == "COMPLETED" and g.get("outputUrl"):
            api.download(g["outputUrl"], out)
            res["file"] = str(out.relative_to(ex))
        print(f"{job['name']}: {g['status']} {g.get('error') or ''}", flush=True)
        return res
    except Exception as e:  # keep going; record the failure
        print(f"{job['name']}: ERROR {e}", flush=True)
        return {**job, "status": "ERROR", "error": str(e)}


def lipsync(exch: str, workers: int = 6) -> None:
    ex = Path(exch)
    clips = {c["clip"]: c["frames"] for c in json.loads((ex / "clips.json").read_text())}
    jobs = json.loads((ex / "lipsync_jobs.json").read_text())
    man_p = ex / "lipsync" / "manifest.json"
    done = {r["name"]: r for r in load_json(man_p, []) if r.get("status") == "COMPLETED" and (ex / r.get("file", "x")).exists()}
    todo = [j for j in jobs if j["name"] not in done]
    print(f"{len(jobs)} jobs, {len(done)} already done, {len(todo)} to run", flush=True)
    results = dict(done)
    # Wave 1: independent jobs. Wave 2: jobs chained on a wave-1 output (second speaker in a shot).
    for wave in ([j for j in todo if not j.get("input_from")], [j for j in todo if j.get("input_from")]):
        with ThreadPoolExecutor(max_workers=workers) as pool:  # Growth plan: 6 concurrent
            for r in pool.map(lambda j: run_job(j, ex, clips), wave):
                results[r["name"]] = r
                save_json(man_p, list(results.values()))
    bad = [r for r in results.values() if r.get("status") != "COMPLETED"]
    print(f"finished: {len(results) - len(bad)} completed, {len(bad)} not completed", flush=True)
    for r in bad:
        print("  ", r["name"], r.get("status"), r.get("errorCode"), (r.get("error") or "")[:200])


# ------------------------------------------------------------------ line fixes (re-voice wrong dub lines)

def fixes(exch: str) -> None:
    """Clone each character's dub voice (exchange/full/fix_inputs/voice_<char>.wav) and TTS every fix line.

    fixes.json: {"characters": {"<char>": {...}}, "lines": [{"id", "character", "tts", ...}]}
    Writes fix_tts/<id>_t<k>.mp3 and fix_tts/manifest.json. Reruns skip finished takes and reuse clones.
    """
    ex = Path(exch)
    cfg = json.loads((ex / "fixes.json").read_text())
    man_p = ex / "fix_tts" / "manifest.json"
    man = load_json(man_p, {"voices": {}, "takes": []})
    have = {t["file"] for t in man["takes"] if (ex / t["file"]).exists()}
    existing = {v.get("name"): v for v in api.list_voices()}
    for char in sorted({ln["character"] for ln in cfg["lines"]}):
        if char in man["voices"]:
            continue
        name = f"Raven dub - {char}"
        if name in existing:
            v = existing[name]
            man["voices"][char] = {"voiceId": v.get("voiceId") or v.get("id"), "name": name, "reused": True}
        else:
            asset = api.upload(ex / "fix_inputs" / f"voice_{char}.wav", name=f"{name} sample", project_id=PROJECT_ID)
            v = api.clone_voice(name, asset_id=asset["id"])
            man["voices"][char] = {"voiceId": v["voiceId"], "syncId": v["id"], "name": name}
        print("voice", char, man["voices"][char]["voiceId"], flush=True)
        save_json(man_p, man)
    takes = [(0.35, 0.95), (0.5, 0.95), (0.7, 0.9)]
    for ln in cfg["lines"]:
        vid = man["voices"][ln["character"]]["voiceId"]
        for k, (st, sim) in enumerate(takes):
            rel = f"fix_tts/{ln['id']}_t{k}.mp3"
            if rel in have:
                continue
            for attempt in range(4):
                try:
                    r = api.tts(ln["tts"], vid, stability=st, similarity=sim)
                    break
                except RuntimeError as e:
                    print(ln["id"], e, flush=True); time.sleep(5 * (attempt + 1))
            else:
                continue
            api.download(r["url"], ex / rel)
            man["takes"].append({"id": ln["id"], "take": k, "stability": st, "similarity": sim, "file": rel,
                                 "duration": r.get("duration"), "text": ln["tts"]})
            save_json(man_p, man)
            print("tts", rel, r.get("duration"), flush=True)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "dub":
        dub(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "lipsync":
        lipsync(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "fixes":
        fixes(sys.argv[2])
    else:
        print(__doc__)
