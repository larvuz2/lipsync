"""Minimal sync. labs API client for the dubbing tests.

Reads the key from the SYNC_API_KEY environment variable (never hard-code it).
Endpoints and field names follow https://sync.so/docs/openapi.json.

Quick check that the key works (free, no generation):
    python3 tools/sync_api.py check
"""

from __future__ import annotations

import mimetypes
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.sync.so"
TERMINAL = {"COMPLETED", "FAILED", "REJECTED"}


def _key() -> str:
    key = os.environ.get("SYNC_API_KEY", "").strip()
    if not key:
        sys.exit("SYNC_API_KEY is not set. Add it as an environment variable (see PLAN.md).")
    return key


def _req(method: str, path: str, **kw):
    r = requests.request(method, BASE + path, headers={"x-api-key": _key()}, timeout=120, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.content else None


# --- assets -----------------------------------------------------------------

def upload(path: str | Path, name: str | None = None) -> dict:
    """Upload a local file into Sync storage and register it. Returns the Asset (has 'id' and 'url')."""
    p = Path(path)
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    kind = "VIDEO" if ctype.startswith("video") else "AUDIO" if ctype.startswith("audio") else "IMAGE"
    pre = _req("POST", "/v2/assets/upload",
               json={"fileName": p.name, "contentType": ctype, "size": p.stat().st_size})
    with open(p, "rb") as fh:  # presigned PUT: no API key, same Content-Type
        put = requests.put(pre["uploadUrl"], data=fh, headers={"Content-Type": ctype}, timeout=600)
    put.raise_for_status()
    return _req("POST", "/v2/assets", json={"url": pre["url"], "type": kind, "name": name or p.name})


# --- lip sync ---------------------------------------------------------------

def generate(body: dict) -> dict:
    return _req("POST", "/v2/generate", json=body)


def estimate(body: dict) -> dict:
    return _req("POST", "/v2/generations/estimate", json=body)


def wait_generation(gen_id: str, every: float = 10) -> dict:
    while True:
        g = _req("GET", f"/v2/generate/{gen_id}")
        if g["status"] in TERMINAL:
            return g
        time.sleep(every)


# --- audio: transcription, voices, TTS, dubbing ------------------------------

def transcribe(source_url: str, video: bool = True) -> dict:
    key = "sourceVideoUrl" if video else "sourceAudioUrl"
    job = _req("POST", "/v2/transcriptions", json={key: source_url})
    while job["status"] not in {"COMPLETED", "FAILED"}:
        time.sleep(5)
        job = _req("GET", f"/v2/transcriptions/{job['id']}")
    return job


def list_voices() -> list:
    return _req("GET", "/v2/voices")


def clone_voice(name: str, asset_id: str | None = None, sample_urls: list[str] | None = None) -> dict:
    body: dict = {"name": name, "provider": "elevenlabs"}
    if asset_id:
        body["assetId"] = asset_id
    elif sample_urls:
        body["sampleUrls"] = sample_urls[:10]
    else:
        raise ValueError("need asset_id or sample_urls")
    return _req("POST", "/v2/voices", json=body)


def delete_voice(sync_voice_uuid: str) -> None:
    _req("DELETE", f"/v2/voices/{sync_voice_uuid}")


def tts(script: str, voice_id: str, stability: float = 0.5, similarity: float = 0.8) -> dict:
    return _req("POST", "/v2/tts", json={"script": script, "voiceId": voice_id, "provider": "elevenlabs",
                                         "stability": stability, "similarityBoost": similarity})


def dub_audio(audio_asset_id: str, target: str = "en-US", source: str = "hu", strength: int = 7) -> dict:
    job = _req("POST", "/v2/integrations/dubbing",
               json={"audioAssetId": audio_asset_id, "targetLang": target, "sourceLang": source,
                     "providerName": "elevenlabs", "cloningStrength": strength})
    while job["status"] not in {"COMPLETED", "FAILED"}:
        time.sleep(5)
        job = _req("GET", f"/v2/integrations/dubbing/{job['id']}")
    return job


def download(url: str, dest: str | Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return dest


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        models = _req("GET", "/v2/models")
        names = [m.get("name") or m.get("id") or m for m in (models if isinstance(models, list) else models.get("data", []))]
        print("Key OK. Models available to this account:", names)
        print("Voices visible:", len(list_voices()))
    else:
        print(__doc__)
