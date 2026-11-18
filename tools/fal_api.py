"""Small fal.ai helper (reads FAL_KEY from the environment; never print or log it).

    import fal_api
    url = fal_api.upload("work/x.wav")
    res = fal_api.run("fal-ai/elevenlabs/dubbing", {"audio_url": url, "target_lang": "en"})
    fal_api.download(res["audio"]["url"], "work/out.mp3")
"""
import os
import time
from pathlib import Path

import fal_client
import requests


def upload(path) -> str:
    for attempt in range(4):
        try:
            return fal_client.upload_file(str(path))
        except Exception as e:  # network hiccups
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def run(endpoint: str, args: dict, log=print) -> dict:
    def on_update(u):
        if isinstance(u, fal_client.InProgress) and u.logs:
            for item in u.logs:
                log(f"  [{endpoint}] {item.get('message', '')}")
    return fal_client.subscribe(endpoint, arguments=args, with_logs=True, on_queue_update=on_update)


def download(url: str, dest) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return dest
