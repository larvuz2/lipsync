"""Jacket swap with video-EDIT models on fal (the source video is the base; only the jacket should change).

    python3 tools/pp_edit_models.py <model> [tag]      model: kling4 | klingo3 | happyhorse | wan27

Input: work/pp/src/edit_in_8s.mp4 (the 8 s after the first 5 s, original 23.976 fps, 192 frames) and the
product photo work/pp/jacket.png. Output: work/pp/edit/<tag>.mp4 (+ .json with the prompt and request).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import fal_api  # noqa: E402

VIDEO, JACKET = "work/pp/src/edit_in_8s.mp4", "work/pp/jacket.png"

JACKET_DESC = ("white lightweight hooded full-zip track jacket with a fine perforated mesh texture, a black zipper, "
               "black piping along both front edges and around the hood opening, black trim at the cuffs and hem, "
               "black-and-white branded tape inside the hood, and a small black adidas logo on the left chest")


def prompt(video_ref, image_ref):
    return (
        f"Edit {video_ref}. Replace ONLY the olive-green military shirt-jacket worn by the grey-haired middle-aged man "
        f"holding the gold bucket with the jacket shown in {image_ref}, in every shot where he appears. Reproduce the "
        f"jacket from {image_ref} exactly: {JACKET_DESC}. He wears it open over his same white graphic T-shirt and "
        f"necklaces, hood down behind his neck; it fits him and folds and moves naturally with his body. "
        f"Everything else stays exactly identical to {video_ref}, frame by frame: his face, identity, skin, hair, "
        f"facial expressions, eye movements, mouth and lip movements on every frame, head, arm and hand motion and "
        f"their timing, the gold bucket, every other person and their clothing, the background, the camera framing "
        f"and camera movement, the shot cuts at the same moments, the speed, the lighting, the colour grade and the "
        f"film grain. Do not add, remove, restyle, re-time or re-animate anything else."
    )


def main():
    model = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else model
    cache = "work/pp/edit/uploads.json"
    try:
        up = json.load(open(cache))
    except Exception:
        up = {}
    if "video" not in up:
        up = {"video": fal_api.upload(VIDEO), "jacket": fal_api.upload(JACKET)}
        json.dump(up, open(cache, "w"))
    if model == "kling4":
        ep = "kling/v4/video-to-video/edit"
        args = {"video_url": up["video"], "image_urls": [up["jacket"]], "prompt": prompt("@Video1", "@Image1"),
                "resolution": "1080p", "keep_audio": True}
    elif model == "klingo3":
        ep = "fal-ai/kling-video/o3/pro/video-to-video/edit"
        args = {"video_url": up["video"], "image_urls": [up["jacket"]], "prompt": prompt("@Video1", "@Image1"),
                "keep_audio": True}
    elif model == "happyhorse":
        ep = "alibaba/happy-horse/video-edit"
        args = {"video_url": up["video"], "reference_image_urls": [up["jacket"]], "prompt": prompt("the video", "@Image1"),
                "resolution": "1080p", "audio_setting": "origin"}
    elif model == "wan27":
        ep = "fal-ai/wan/v2.7/edit-video"
        args = {"video_url": up["video"], "reference_image_url": up["jacket"],
                "prompt": prompt("the video", "the reference image"), "resolution": "1080p", "audio_setting": "origin"}
    else:
        raise SystemExit("unknown model " + model)
    t0 = time.time()
    res = fal_api.run(ep, args, log=lambda *a: None)
    url = (res.get("video") or {}).get("url")
    fal_api.download(url, f"work/pp/edit/{tag}.mp4")
    json.dump({"endpoint": ep, "args": {k: v for k, v in args.items() if not k.endswith("url") and not k.endswith("urls")},
               "seed": res.get("seed"), "elapsed_s": round(time.time() - t0)}, open(f"work/pp/edit/{tag}.json", "w"), indent=1)
    print("saved", tag, "in", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
