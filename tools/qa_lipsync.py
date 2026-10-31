"""Check each finished lip-sync job: did it change the pinned face (and nothing else)?

    python3 tools/qa_lipsync.py exchange/full media/full [job ...]

Per job: average change map (output vs original frames), centre of the changed area, distance to the
pinned face point, share of changed pixels far from that face. Also writes qa/<job>.jpg: three frames,
original vs lip-synced crop around the face, for a visual check.
"""
import glob
import json
import os
import subprocess
import sys

import cv2
import numpy as np

W, H = 960, 540


def frames(path, first=0, n=None, scale=True):
    vf = f"select='gte(n,{first})'," if first else ""
    vf += f"scale={W}:{H}" if scale else "null"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-vsync", "0", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, H if scale else 1080, W if scale else 1920, 3)
    return a[:n] if n else a


def main():
    ex, media = sys.argv[1], sys.argv[2]
    only = set(sys.argv[3:])
    man = json.load(open(os.path.join(ex, "lipsync", "manifest.json")))
    os.makedirs(os.path.join(ex, "qa"), exist_ok=True)
    out = []
    for j in man:
        if j.get("status") != "COMPLETED" or (only and j["name"] not in only):
            continue
        src = glob.glob(os.path.join(media, f"*Splits{j['clip']}.mp4"))[0]
        o = frames(os.path.join(ex, j["file"]))
        base = os.path.join(ex, "lipsync", "out", f"{j['input_from']}.mp4") if j.get("input_from") else None
        s = frames(base) if base else frames(src, j["first_frame"], len(o))
        n = min(len(o), len(s))
        d = np.abs(o[:n].astype(np.int16) - s[:n].astype(np.int16)).mean(3)
        m = d.mean(0)
        mask = m > max(3.0, np.percentile(m, 99.5) * 0.4)
        fx, fy = j["face"]["xy"][0] / 2, j["face"]["xy"][1] / 2
        ys, xs = np.where(mask)
        if len(xs):
            cx, cy = xs.mean(), ys.mean()
            dist = float(np.hypot(cx - fx, cy - fy)) * 2
            far = float(np.mean(np.hypot(xs - fx, ys - fy) * 2 > 400))
        else:
            cx = cy = dist = far = None
        r = {"name": j["name"], "changed_px": int(mask.sum()), "center_full": None if cx is None else [int(cx * 2), int(cy * 2)],
             "pin": j["face"]["xy"], "dist_px": None if dist is None else round(dist), "far_share": None if far is None else round(far, 2)}
        r["verdict"] = "OK" if dist is not None and dist < 260 and far < 0.25 else "CHECK"
        out.append(r)
        print(json.dumps(r), flush=True)
        # visual sheet: original vs output crops around the changed area (or the pin)
        ccx, ccy = (cx, cy) if cx is not None else (fx, fy)
        tiles = []
        for k in [n // 6, n // 2, (5 * n) // 6]:
            row = []
            for img in (s[k], o[k]):
                x0, y0 = int(max(0, ccx - 90)), int(max(0, ccy - 90))
                crop = cv2.resize(img[y0:y0 + 180, x0:x0 + 180], (240, 240))
                row.append(crop)
            tiles.append(np.hstack(row))
        sheet = np.hstack(tiles)
        cv2.putText(sheet, f"{j['name']} {r['verdict']} (orig|sync per pair)", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cv2.imwrite(os.path.join(ex, "qa", f"{j['name']}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    json.dump(out, open(os.path.join(ex, "qa", "qa.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
