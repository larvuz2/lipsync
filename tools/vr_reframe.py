"""Landscape -> vertical (9:16) reframe of the 15 s Melody clip with fal outpainting models.

    python3 tools/vr_reframe.py luma A|B      (Luma Ray 3.2 Reframe; max 10 s per call -> two halves split at the cut)
    python3 tools/vr_reframe.py minimax       (MiniMax H3 Max Reframe Video; whole 15 s)

Inputs: work/vr/src/in15.mp4 (360 frames, 23.976 fps), inA.mp4 (frames 0-179), inB.mp4 (180-359; the cut at 180).
The whole 16:9 picture is kept (contain-fit, centred) and the canvas above and below is generated. Neither model
takes reference images, so the prompt describes the station and every character's clothes, to be continued exactly.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import fal_api  # noqa: E402

SCENE = ("Vertical 9:16 version of a live-action TV drama scene filmed in a modern metro station concourse. Extend "
         "the picture above and below with exactly the same scene, the same set and the same moment: light grey and "
         "white tiled walls with a purple stripe, a white ceiling with recessed lights, a polished light grey floor "
         "with a yellow tactile strip, the same lighting, colour grade, lens, shallow depth of field and film grain. "
         "Continue every person's body and clothing exactly as it appears in the frame; do not change, add or remove "
         "any clothing, person or object. Photorealistic, no text, no borders, no frames. ")
CAST_A = ("The man with glasses and a short beard wears a light-blue short-sleeve polo shirt with a small red logo, "
          "dark trousers and dark shoes, and pushes a large brown cardboard box with a red strap on a black hand truck; "
          "in the low-angle shot he looks up past the box toward a white ceiling with recessed lights. "
          "Two young women at a microphone stand: a blonde with long wavy hair in a red-and-black plaid flannel shirt, "
          "and a dark-haired woman with a high ponytail in a black leather vest over an orange floral dress, holding "
          "gold fairy lights and a gold bag. A grey-haired man in an olive-green military shirt-jacket over a white "
          "T-shirt, blue jeans and dark shoes lunges toward them; a keyboard on a stand with fairy lights, a laptop, "
          "posters on the wall, commuters walking.")
CAST_B = ("The man with glasses and a short beard in a light-blue short-sleeve polo shirt with a small red logo and "
          "dark trousers bends over a brown cardboard box with a red strap; commuters walk past: a woman in a dark "
          "floral blouse and brown trousers, a woman in a grey tank top and light grey trousers, people in white "
          "hoodies and jeans, stairs and gates behind. Then two young women crouch on a grey tiled floor between tall "
          "stacks of newspapers against a grey-green wall: the dark-haired woman with a high ponytail in an orange "
          "floral dress over a black top, brown socks and white platform high-top sneakers; the blonde in a "
          "red-and-black plaid flannel shirt, black shorts and black ankle boots; both hold glowing gold fairy lights.")


def main():
    model = sys.argv[1]
    part = sys.argv[2] if len(sys.argv) > 2 else ""
    if model == "luma":
        src = f"work/vr/src/in{part}.mp4"
        ep = "luma/agent/ray/v3.2/reframe"
        args = {"prompt": SCENE + (CAST_A if part == "A" else CAST_B), "aspect_ratio": "9:16", "resolution": "720p"}  # 1080p not offered for 9:16
        tag = f"luma_{part}"
    elif model == "minimax":
        src = "work/vr/src/in15.mp4"
        ep = "minimax/h3-max/reframe-video"
        args = {"prompt": SCENE + CAST_A + " " + CAST_B, "aspect_ratio": "9:16", "resolution": "1080p"}
        tag = "minimax"
    else:
        raise SystemExit("model: luma A|B or minimax")
    args["video_url"] = fal_api.upload(src)
    t0 = time.time()
    res = fal_api.run(ep, args, log=lambda *a: None)
    fal_api.download(res["video"]["url"], f"work/vr/gen/{tag}.mp4")
    json.dump({"endpoint": ep, "prompt": args["prompt"], "aspect_ratio": "9:16", "resolution": args["resolution"],
               "seed": res.get("seed"), "elapsed_s": round(time.time() - t0)}, open(f"work/vr/gen/{tag}.json", "w"), indent=1)
    print("saved", tag, "in", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
