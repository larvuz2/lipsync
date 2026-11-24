"""Restyle the 9.1 s dialogue clip into the animated version with the two character sheets as references.

    python3 tools/anim_video.py seedance|klingo3 [tag]

@Image1 = the blonde girl's sheet (work/anim/sheets/melody_0.png), @Image2 = the dark-haired girl's sheet (layla_0.png).
Seedance 2.5 (editing) gets the clip re-tagged to 24 fps (it needs >= 24 fps; frames are the same 218);
Kling O3 Pro video edit gets the clip at its own 23.976 fps. No audio is generated; the original sound is used.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import fal_api  # noqa: E402

PROMPT = (
    "Turn @Video1 into a stylized 3D animated feature film version of exactly the same scene. The blonde girl with "
    "long wavy hair in the red-and-black plaid shirt becomes the animated character in @Image1; the dark-haired girl "
    "with the high half-ponytail and the black studded leather vest over an orange floral top becomes the animated "
    "character in @Image2 - same faces, hair and outfits as their character sheets, in that same animation style. "
    "Keep everything else exactly as in @Video1, frame by frame: the same shots and cuts at the same moments, the same "
    "camera framing and camera movement, the same poses, gestures, head turns and eye lines, the same facial "
    "expressions, and the same mouth and lip movements on every frame, so the animated characters speak exactly the "
    "same dialogue in sync with the original timing. The same set - a small radio corner in a metro station with a "
    "blue neon ring light, a pink 'Retro' sign, colourful posters, fairy lights and a microphone on a stand - restyled "
    "to match the animation, with the same lighting mood and colours. Do not add or remove anyone or anything; no "
    "text, no subtitles, no captions."
)


def main():
    model = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else model
    sheets = [fal_api.upload("work/anim/sheets/melody_0.png"), fal_api.upload("work/anim/sheets/layla_0.png")]
    if model == "seedance":
        ep = "bytedance/seedance-2.5/us/reference-to-video"
        args = {"task": "editing", "prompt": PROMPT, "video_urls": [fal_api.upload("work/anim/src/in_24.mp4")],
                "image_urls": sheets, "resolution": "1080p", "bitrate_mode": "high", "generate_audio": False,
                "aspect_ratio": "auto", "duration": "auto"}
    elif model == "klingo3":
        ep = "fal-ai/kling-video/o3/pro/video-to-video/edit"
        args = {"prompt": PROMPT, "video_url": fal_api.upload("work/anim/src/in.mp4"), "image_urls": sheets, "keep_audio": True}
    else:
        raise SystemExit("seedance | klingo3")
    t0 = time.time()
    res = fal_api.run(ep, args, log=lambda *a: None)
    fal_api.download(res["video"]["url"], f"work/anim/gen/{tag}.mp4")
    json.dump({"endpoint": ep, "prompt": PROMPT, "seed": res.get("seed"), "elapsed_s": round(time.time() - t0)},
              open(f"work/anim/gen/{tag}.json", "w"), indent=1)
    print("saved", tag, "in", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
