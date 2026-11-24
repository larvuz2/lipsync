"""Compare jacket-swap outputs with the original 8 s: timing, face/mouth and background exactness.

    python3 tools/pp_eval_edits.py work/pp/edit/kling4.mp4 [more.mp4 ...]

For each output: frames/fps; best time offset per shot (in original frames; 0 = in sync with the audio);
face difference (his head region, from the original's SAM person mask minus jacket, top part) and background
difference (outside his body) vs the original frame at the same time, at 960x540, mean abs (0-255).
"""
import json
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__file__))
from pp_rle import decode  # noqa: E402

FPS = 24000 / 1001
SHOTS = [(0, 65, "1"), (66, 112, "2"), (156, 191, "4")]


def probe(p):
    s = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames,r_frame_rate,width,height", "-of", "json", p], capture_output=True, text=True).stdout
    st = json.loads(s)["streams"][0]
    n, d = st["r_frame_rate"].split("/")
    return int(st["nb_read_frames"]), float(n) / float(d), st["width"], st["height"]


def frames(p, w=960, h=540):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(np.float32)


def regions():
    face, bg = {}, {}
    for o0, o1, nm in SHOTS:
        P = [decode(x) for x in json.load(open(f"work/pp/sam/o{nm}_res.json"))["rle"]]
        J = [decode(x) for x in json.load(open(f"work/pp/sam/o{nm}_jk_res.json"))["rle"]]
        for j in range(o1 - o0 + 1):
            p = cv2.resize(P[j], (960, 540), interpolation=cv2.INTER_NEAREST).astype(bool)
            jk = cv2.resize(J[j], (960, 540), interpolation=cv2.INTER_NEAREST).astype(bool)
            ys = np.where(p.any(1))[0]
            top = ys.min() if len(ys) else 0
            # head = person pixels, not jacket, above the jacket's top + a bit
            jy = np.where(jk.any(1))[0]
            cut = (jy.min() + 25) if len(jy) else top + 120
            head = p & ~jk
            head[cut:] = False
            face[o0 + j] = head
            bg[o0 + j] = ~cv2.dilate(p.astype(np.uint8), np.ones((25, 25), np.uint8)).astype(bool)
    return face, bg


def main():
    O = frames("work/pp/src/edit_in_8s.mp4")
    face, bg = regions()
    for path in sys.argv[1:]:
        n, fps, w, h = probe(path)
        G = frames(path)
        # map each original frame to the output frame at the same time
        idx = [min(len(G) - 1, int(round(j / FPS * fps))) for j in range(192)]
        offs = []
        for o0, o1, nm in SHOTS:
            best = []
            for k in range(-8, 9):
                ds = []
                for j in range(o0 + 4, o1 - 4):
                    i = min(max(idx[j] + k, 0), len(G) - 1)
                    ds.append(np.abs(G[i] - O[j])[bg[j]].mean())
                best.append((np.mean(ds), k))
            offs.append(min(best)[1])
        fd = [np.abs(G[idx[j]] - O[j])[face[j]].mean() for j in face if face[j].any()]
        bd = [np.abs(G[idx[j]] - O[j])[bg[j]].mean() for j in bg]
        print(f"{path}: {n} frames @ {fps:.3f} fps {w}x{h} ({n / fps:.2f} s) | best offset per shot (frames, + = output late): "
              f"{offs} | face diff {np.mean(fd):.1f} | background diff {np.mean(bd):.1f}")


if __name__ == "__main__":
    main()
