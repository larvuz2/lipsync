"""Second, more careful Hungarian pass for hard clips (whispers, shouts, names).

    python3 tools/retranscribe_hu.py exchange/full media/full 00090527 00104461 ...

Whisper large-v3 with a vocabulary prompt of the show's names and period words, beam 8, plus a
louder copy for whispered lines. Writes exchange/full/transcripts_hu2.json.
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel

PROMPT = ("Hunyadi János, Jankó, Vajk, Szilágyi Erzsébet, Szilágyi Mihály, Zsigmond király, Borbála királyné, "
          "Lazarevics István, szerb despota, karvas, íj, ideg, farkas, frajla, menyasszony, vár, uram, apám, anyám, "
          "kapu, gyerünk, mozgás.")


def pcm16(path, gain_db=0):
    af = ["-af", f"volume={gain_db}dB,alimiter=limit=0.9"] if gain_db else []
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", *af, "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def main():
    ex, media, clips = sys.argv[1], sys.argv[2], sys.argv[3:]
    out_p = os.path.join(ex, "transcripts_hu2.json")
    out = json.load(open(out_p)) if os.path.exists(out_p) else {}
    m = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    for c in clips:
        path = glob.glob(os.path.join(media, f"*Splits{c}.mp4"))[0]
        res = {}
        for label, g in (("normal", 0), ("boosted", 12)):
            segs, _ = m.transcribe(pcm16(path, g), language="hu", beam_size=8, initial_prompt=PROMPT,
                                   condition_on_previous_text=False, temperature=0.0)
            res[label] = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs]
        out[c] = res
        json.dump(out, open(out_p, "w"), indent=1, ensure_ascii=False)
        print(c, "|", " / ".join(s["text"] for s in res["normal"]), "||", " / ".join(s["text"] for s in res["boosted"]), flush=True)


if __name__ == "__main__":
    main()
