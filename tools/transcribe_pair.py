"""Whisper transcripts of every clip: Hungarian original and English dub, with word timings.

    python3 tools/transcribe_pair.py exchange/full media/full     -> exchange/full/transcripts.json
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel


def pcm16(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def run(model, x, lang):
    segs, _ = model.transcribe(x, language=lang, word_timestamps=True, beam_size=5, condition_on_previous_text=False)
    return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
             "words": [[round(w.start, 2), round(w.end, 2), w.word.strip(), round(w.probability, 2)] for w in (s.words or [])]}
            for s in segs]


def main():
    ex, media = sys.argv[1:3]
    out_p = os.path.join(ex, "transcripts.json")
    done = json.load(open(out_p)) if os.path.exists(out_p) else {}
    model = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    for c in json.load(open(os.path.join(ex, "clips.json"))):
        cid = c["clip"]
        if cid in done:
            continue
        hu = run(model, pcm16(glob.glob(os.path.join(media, f"*Splits{cid}.mp4"))[0]), "hu")
        en = run(model, pcm16(os.path.join(ex, "en", f"{cid}_EN.wav")), "en")
        done[cid] = {"hu": hu, "en": en}
        json.dump(done, open(out_p, "w"), indent=1, ensure_ascii=False)
        print(cid, "| HU:", " / ".join(s["text"] for s in hu), "| EN:", " / ".join(s["text"] for s in en), flush=True)


if __name__ == "__main__":
    main()
