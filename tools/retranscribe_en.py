"""Re-transcribe the English tracks of clips whose dub was fixed, for word-level speaker gating.

    python3 tools/retranscribe_en.py exchange/full 00090527 00102229 ...

Starts from transcripts.json (Hungarian + original dub) and replaces "en" for the given clips with a
transcript of the current en/<clip>_EN.wav. Writes exchange/full/transcripts_en_final.json.
"""
import json
import os
import sys

from faster_whisper import WhisperModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transcribe_pair import pcm16, run  # noqa: E402


def main():
    ex, clips = sys.argv[1], sys.argv[2:]
    out_p = os.path.join(ex, "transcripts_en_final.json")
    base = json.load(open(os.path.join(ex, "transcripts.json")))
    if os.path.exists(out_p):
        base.update(json.load(open(out_p)))
    model = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    for c in clips:
        en = run(model, pcm16(os.path.join(ex, "en", f"{c}_EN.wav")), "en")
        base[c] = {**base[c], "en": en, "en_fixed": True}
        json.dump(base, open(out_p, "w"), indent=1, ensure_ascii=False)
        print(c, "| EN:", " / ".join(f"{s['start']:.1f}-{s['end']:.1f} {s['text']}" for s in en), flush=True)


if __name__ == "__main__":
    main()
