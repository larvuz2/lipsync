"""python3 tools/pp_seedance.py <tag> open

Seedance 2.5 (fal) jacket swap: edit the 8 s reference video, only the grey-haired man's jacket changes."""
import json, sys, time
sys.path.insert(0, __import__("os").path.dirname(__file__))
import fal_api

tag = sys.argv[1]
variant = sys.argv[2] if len(sys.argv) > 2 else "open"
JACKET = "work/pp/jacket.png"  # the product photo
cache = "work/pp/gen/uploads.json"
try:
    up = json.load(open(cache))
except Exception:
    up = {}
if "video" not in up:
    up["video"] = fal_api.upload("work/pp/src/seed_in_8s_24fps.mp4")
    up["jacket"] = fal_api.upload(JACKET)
    json.dump(up, open(cache, "w"))

WEAR = {
    "open": "He wears the new jacket open and unzipped exactly the way he wears the original jacket, hanging open over the same white graphic T-shirt, "
            "so the black zipper tape and black trim run down both open front edges and the small black adidas logo stays visible on his left chest.",
}[variant]

prompt = (
    "Video edit of @Video1. Keep @Video1 completely identical frame by frame: the same people, the same faces, the same facial expressions, "
    "the same mouth and lip movements, the same eye movements, the same head, hand and body motion and timing, the same gold bucket, "
    "the same camera framing and camera movement, the same shot cuts at the same moments, the same background, crowd, lighting, colour grade, "
    "film grain and focus. Change exactly one thing: the olive-green military shirt-jacket worn by the middle-aged man with grey hair "
    "(the man holding the gold bucket with the photo on it, who appears in the close shots and on the right of the wide shots) is replaced "
    "by the exact white jacket shown in @Image1. Reproduce the jacket from @Image1 precisely: a white lightweight hooded full-zip track jacket "
    "with a fine perforated mesh texture, a black zipper, thin black piping around the hood opening, the cuffs and the hem, "
    "black-and-white branded tape inside the hood, and a small black adidas logo (three slanted bars with the word adidas) on the left chest. "
    "The hood lies down behind his neck. " + WEAR + " "
    "The new jacket fits him naturally, folds and moves with his body exactly as the original jacket did, and is lit by the same scene lighting. "
    "Do not change anyone else's clothing: every other person, including the person in the yellow-green top and the girls, keeps exactly the "
    "same clothes. Do not add or remove any object, text or person. No new camera moves, no zoom, no style change."
)
args = {
    "task": "editing",
    "prompt": prompt,
    "video_urls": [up["video"]],
    "image_urls": [up["jacket"]],
    "resolution": "1080p",
    "bitrate_mode": "high",
    "generate_audio": False,
    "aspect_ratio": "auto",
    "duration": "auto",
}
t0 = time.time()
res = fal_api.run("bytedance/seedance-2.5/us/reference-to-video", args)
print("elapsed", round(time.time() - t0), "s")
url = res["video"]["url"]
fal_api.download(url, f"work/pp/gen/{tag}.mp4")
json.dump({"tag": tag, "variant": variant, "prompt": prompt, "seed": res.get("seed"), "result_keys": list(res.keys())},
          open(f"work/pp/gen/{tag}.json", "w"), indent=1)
print("saved", tag, "seed", res.get("seed"))
