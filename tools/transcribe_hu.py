"""Transcribe the Hungarian dialogue of every .mp4 in a folder with Whisper large-v3 (CPU).

    pip install faster-whisper
    python3 tools/transcribe_hu.py "media/LIP SYNC TEST" data/transcript_hu_whisper.json

Output: {clip_number: [{start, end, text, words: [[start, end, word], ...]}, ...]}
Timings are seconds from the start of each clip. A native speaker should check the text.
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel

src, out = sys.argv[1], sys.argv[2]
model = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
result = {}
for f in sorted(glob.glob(os.path.join(src, "*.mp4"))):
    key = f.split("Splits")[-1].removesuffix(".mp4")
    # Decode with ffmpeg ourselves (faster-whisper's PyAV path breaks on some versions).
    pcm = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vn", "-ac", "1", "-ar", "16000",
                                        "-f", "f32le", "-"], capture_output=True, check=True).stdout, dtype=np.float32)
    segments, _ = model.transcribe(pcm, language="hu", word_timestamps=True, beam_size=5)
    result[key] = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                    "words": [[round(w.start, 2), round(w.end, 2), w.word.strip()] for w in (s.words or [])]}
                   for s in segments]
    print(key, " | ".join(s["text"] for s in result[key]), flush=True)
json.dump(result, open(out, "w"), ensure_ascii=False, indent=1)
