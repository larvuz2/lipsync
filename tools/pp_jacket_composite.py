"""Lay the generated jacket onto the original frames, so faces, lips, hands and crowd stay the original.

The generated video (Seedance 2.5 edit) keeps the shots and the acting but is not frame-exact: 185 frames for the
original 192 and small pose/position differences. Per shot:
  1. time: each original frame is matched to a generated frame (monotonic DTW on the picture with both jackets
     flattened to grey, so the jacket colour does not drive the match);
  2. space: dense optical flow (DIS) from the original frame to its generated frame, again with both jackets
     flattened (the silhouettes, head, hands, T-shirt and bucket drive the flow); the generated frame is warped
     onto the original's geometry;
  3. composite: inside (original jacket OR warped generated jacket), feathered, minus his head/neck, the warped
     generated pixels; everywhere else the original pixels.
Shots without him (the box shot) stay original.

    python3 tools/pp_jacket_composite.py <orig13.mkv> <gen.mp4> <out_swap8.mkv> [debug_dir]
"""
import json
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__file__))
from pp_rle import decode  # noqa: E402

W, H = 1920, 1080
SWITCH = 120
SP_SIGMA = float(__import__("os").environ.get("PP_SP_SIGMA", 6))   # flow blur in space (half-res px)
T_SIGMA = float(__import__("os").environ.get("PP_T_SIGMA", 2.5))   # flow smoothing in time (frames)
# (orig first, orig last, gen first, gen last, sam clip names) in 8 s-clip frame numbers
SHOTS = [(0, 65, 0, 62, "1"), (66, 112, 63, 110, "2"), (156, 191, 150, 184, "4")]


def read_frames(path, start=0, count=None, vf=None):
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
    return f[start:start + count] if count else f[start:]


def masks(name, tag):
    r = json.load(open(f"work/pp/sam/{name}{tag}_res.json"))["rle"]
    return np.stack([decode(x if isinstance(x, str) else "") for x in r]).astype(bool)


def clean_jacket(J, P):
    """Keep only jacket pixels on him: within his (dilated) body mask, components of a useful size."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    out = np.zeros_like(J)
    for i in range(len(J)):
        m = (J[i] & cv2.dilate(P[i].astype(np.uint8), k).astype(bool)).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] > 1500
        out[i] = keep[lab]
    return out


def flat(gray, jm):
    g = gray.copy()
    g[jm] = 128
    return g


def dtw(cost):
    n, m = cost.shape
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = cost[i - 1, j - 1] + min(D[i - 1, j - 1], D[i - 1, j] + 0.02, D[i, j - 1] + 0.02)
    i, j, path = n, m, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        k = np.argmin([D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]])
        i, j = (i - 1, j - 1) if k == 0 else ((i - 1, j) if k == 1 else (i, j - 1))
    return path[::-1]


def main():
    orig_path, gen_path, out_path = sys.argv[1:4]
    dbg = sys.argv[4] if len(sys.argv) > 4 else None
    O = read_frames(orig_path)[SWITCH:SWITCH + 192]
    G = read_frames(gen_path)
    assert len(O) == 192, len(O)
    out = O.copy()
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    dis.setFinestScale(1)
    report = []
    for (o0, o1, g0, g1, nm) in SHOTS:
        OJ = clean_jacket(masks("o" + nm, "_jk"), masks("o" + nm, ""))
        OP = masks("o" + nm, "")
        GJ = clean_jacket(masks("g" + nm, "_jk"), masks("g" + nm, ""))
        no, ng = o1 - o0 + 1, g1 - g0 + 1
        assert len(OJ) == no and len(GJ) == ng, (nm, len(OJ), no, len(GJ), ng)
        # 1. time
        small = lambda im, jm: cv2.resize(flat(cv2.cvtColor(im, cv2.COLOR_RGB2GRAY), jm), (240, 135),
                                          interpolation=cv2.INTER_AREA).astype(np.float32)
        so = np.stack([small(O[o0 + j], OJ[j]) for j in range(no)])
        sg = np.stack([small(G[g0 + i], GJ[i]) for i in range(ng)])
        cost = np.abs(so[:, None] - sg[None]).mean((2, 3)) / 255.0
        path = dtw(cost)
        match = {}
        for a, b in path:
            if a not in match or cost[a, b] < cost[a, match[a]]:
                match[a] = b
        # 2. space: flows for the whole shot, then smoothed in time (per-frame flow noise = jacket jitter)
        flows = []
        for j in range(no):
            i = match[j]
            og = cv2.cvtColor(O[o0 + j], cv2.COLOR_RGB2GRAY)
            gg = cv2.cvtColor(G[g0 + i], cv2.COLOR_RGB2GRAY)
            a = cv2.resize(flat(og, OJ[j]), (960, 540), interpolation=cv2.INTER_AREA)
            b = cv2.resize(flat(gg, GJ[i]), (960, 540), interpolation=cv2.INTER_AREA)
            flows.append(cv2.GaussianBlur(dis.calc(a, b, None), (0, 0), SP_SIGMA))
        flows = np.stack(flows)
        if T_SIGMA > 0:
            k = np.exp(-0.5 * (np.arange(-4, 5) / T_SIGMA) ** 2)
            sm = np.zeros_like(flows)
            for j in range(no):
                idx = np.clip(np.arange(j - 4, j + 5), 0, no - 1)
                sm[j] = np.tensordot(k / k.sum(), flows[idx], axes=(0, 0))
            flows = sm
        gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        # 3. composite
        for j in range(no):
            i = match[j]
            og = cv2.cvtColor(O[o0 + j], cv2.COLOR_RGB2GRAY)
            gg = cv2.cvtColor(G[g0 + i], cv2.COLOR_RGB2GRAY)
            fl = cv2.resize(flows[j], (W, H), interpolation=cv2.INTER_LINEAR) * 2.0
            mx, my = gx + fl[..., 0], gy + fl[..., 1]
            warped = cv2.remap(G[g0 + i], mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            wj = cv2.remap(GJ[i].astype(np.uint8) * 255, mx, my, cv2.INTER_LINEAR) > 127
            body = OP[j] & ~OJ[j] & ~wj
            res_before = np.abs(og.astype(np.float32) - gg.astype(np.float32))[body].mean() if body.any() else 0
            res_after = np.abs(og.astype(np.float32) - cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY).astype(np.float32))[body].mean() if body.any() else 0
            M = (OJ[j] | wj).astype(np.uint8)
            M = cv2.morphologyEx(M, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
            M = cv2.dilate(M, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
            A = cv2.GaussianBlur(M.astype(np.float32), (0, 0), 2.0)[..., None]
            out[o0 + j] = np.clip(O[o0 + j] * (1 - A) + warped * A + 0.5, 0, 255).astype(np.uint8)
            report.append((nm, o0 + j, g0 + i, round(float(np.abs(fl).mean()), 2), round(float(res_before), 1), round(float(res_after), 1)))
            if dbg and j in (0, no // 2, no - 1):
                cv2.imwrite(f"{dbg}/c_{o0 + j:03d}.jpg", cv2.cvtColor(np.concatenate([O[o0 + j], out[o0 + j]], 1), cv2.COLOR_RGB2BGR),
                            [cv2.IMWRITE_JPEG_QUALITY, 88])
    for r in report[::4]:
        print(r)
    json.dump(report, open(out_path + ".report.json", "w"))
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", "24000/1001", "-i", "-", "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv420p", out_path],
                           stdin=subprocess.PIPE)
    for f in out:
        enc.stdin.write(f.tobytes())
    enc.stdin.close()
    enc.wait()
    print("wrote", out_path)


if __name__ == "__main__":
    main()
