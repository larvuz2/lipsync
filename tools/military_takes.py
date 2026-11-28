"""Hunyadi voice options ("more military, tough") for the client to choose from: takes for 5 of his lines.

    python3 tools/military_takes.py clyde|designed|own

clyde    - ElevenLabs Eleven v4 (fal), premade "Callum" (intense, husky; fal has no "Clyde"), [commanding] tag, 2 takes/line
designed - MiniMax voice design (fal): a new deep, gravelly, battle-hardened voice; MiniMax Speech 2.8 HD, 1 take/line
own      - the actor's own clone (HUNYADI2, Sync/ElevenLabs), low stability for a harder read, 2 takes/line
Output: work/military/takes/<opt>_<line>_<k>.<ext> and <opt>.json
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(__file__))
import fal_api  # noqa: E402

LINES = [("P1", "So you're Mihai's sister?"),
         ("P2", "Little Erzhebet Seelahjee."),            # Szilágyi, spelled for the TTS
         ("P3", "What are you doing out here?"),
         ("P4", "A thousand pardons, I thought it was about to tear you to shreds."),
         ("P5", "I thought I'd bring something in honor of the king.")]
OUT = "work/military/takes"
DESIGN = ("Deep, low-pitched male voice of a battle-hardened military commander in his early thirties, American "
          "accent. Rough, gravelly texture, chest resonance, stern and clipped delivery, calm authority of a man used "
          "to giving orders on a battlefield. No theatrical shouting.")


def save(url, path):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    open(path, "wb").write(r.content)


def main():
    opt = sys.argv[1]
    log = {"option": opt, "takes": []}
    if opt == "clyde":
        for lid, text in LINES:
            for k, seed in enumerate((11, 29)):
                res = fal_api.run("elevenlabs/tts/eleven-v4", {"text": "[commanding] " + text, "voice": "Callum",
                                                                "stability": 0.35, "similarity_boost": 0.75,
                                                                "language_code": "en", "seed": seed,
                                                                "output_format": "mp3_44100_192"}, log=lambda *a: None)
                p = f"{OUT}/clyde_{lid}_{k}.mp3"
                save(res["audio"]["url"], p)
                log["takes"].append({"line": lid, "k": k, "file": p, "text": text})
                print(p, flush=True)
    elif opt == "designed":
        d = fal_api.run("fal-ai/minimax/voice-design", {"prompt": DESIGN, "preview_text": LINES[3][1]}, log=lambda *a: None)
        vid = d["custom_voice_id"]
        save(d["audio"]["url"], f"{OUT}/designed_preview.mp3")
        log["voice_id"] = vid
        log["design_prompt"] = DESIGN
        for lid, text in LINES:
            res = fal_api.run("fal-ai/minimax/speech-2.8-hd", {"prompt": text, "output_format": "url",
                                                               "voice_setting": {"voice_id": vid, "speed": 1.0, "vol": 1, "pitch": 0}},
                              log=lambda *a: None)
            p = f"{OUT}/designed_{lid}_0.mp3"
            save(res["audio"]["url"], p)
            log["takes"].append({"line": lid, "k": 0, "file": p, "text": text})
            print(p, flush=True)
    elif opt == "own":
        import sync_api as api
        vid = json.load(open("exchange/full/fix_tts/manifest.json"))["voices"]["HUNYADI2"]["voiceId"]
        for lid, text in LINES:
            for k, st in enumerate((0.3, 0.22)):
                for attempt in range(4):
                    try:
                        r = api.tts(text, vid, stability=st, similarity=0.85)
                        break
                    except RuntimeError as e:
                        print(e, flush=True); time.sleep(5 * (attempt + 1))
                p = f"{OUT}/own_{lid}_{k}.mp3"
                save(r["url"], p)
                log["takes"].append({"line": lid, "k": k, "file": p, "text": text, "stability": st})
                print(p, flush=True)
    json.dump(log, open(f"{OUT}/{opt}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
