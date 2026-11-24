"""SAM 3 (fal, RLE) text-prompted masks per shot clip: python3 tools/pp_sam.py <name> <prompt> <tag>"""
import json, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
import fal_api
name, prompt, tag = sys.argv[1], sys.argv[2], sys.argv[3]
url = fal_api.upload(f"work/pp/sam/{name}.mp4")
args = {"video_url": url, "prompt": prompt, "apply_mask": False, "detection_threshold": 0.4}
res = fal_api.run("fal-ai/sam-3/video-rle", args, log=lambda *a: None)
json.dump(res, open(f"work/pp/sam/{name}_{tag}_res.json", "w"))
r = res.get("rle")
print(name, tag, type(r).__name__, len(r) if hasattr(r, "__len__") else "", "meta", str(res.get("metadata"))[:300], "boxes", str(res.get("boxes"))[:200])
print(" first", type(r[0]).__name__, str(r[0])[:120])

# Whole-person masks (used to keep only his jacket and to measure the fit) were made with point prompts:
# import json, sys
# sys.path.insert(0, "tools")
# import fal_api
# name, pts = sys.argv[1], sys.argv[2]
# prompt = sys.argv[3] if len(sys.argv) > 3 else ""
# url = fal_api.upload(f"work/pp/sam/{name}.mp4")
# pp = [{"x": int(p.split(",")[0]), "y": int(p.split(",")[1]), "label": 1, "frame_index": 0, "object_id": 1} for p in pts.split(";")]
# args = {"video_url": url, "point_prompts": pp, "apply_mask": False}
# if prompt:
#     args["prompt"] = prompt
# res = fal_api.run("fal-ai/sam-3/video-rle", args, log=lambda *a: None)
# json.dump(res, open(f"work/pp/sam/{name}_res.json", "w"))
# r = res.get("rle")
# print(name, type(r).__name__, (len(r) if hasattr(r, "__len__") else ""), str(r)[:300])
