"""Decode fal SAM 3 RLE masks (pairs of start, length over the row-major 1920x1080 frame)."""
import json, numpy as np
W, H = 1920, 1080
def decode(s):
    m = np.zeros(W * H, np.uint8)
    if s:
        v = np.array(s.split(), np.int64)
        for a, l in zip(v[0::2], v[1::2]):
            m[a:a + l] = 1
    return m.reshape(H, W)
def load(name):
    r = json.load(open(f"work/pp/sam/{name}_res.json"))["rle"]
    return np.stack([decode(x if isinstance(x, str) else (x[0] if x else "")) for x in r])
