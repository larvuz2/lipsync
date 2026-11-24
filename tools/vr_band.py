"""Put the original 16:9 picture back into the band of an outpainted 9:16 video (1080x1920).

The reframe models fit the source across the full width (1080 x 607.5, centred) and paint above and below. MiniMax H3
Max re-renders the band too (its 1080p is upscaled from 768p and changes faces), so the band is replaced by the
original footage, resized, with a short vertical blend at its top and bottom edges so the model's extension meets
the original without a line. Everything inside the band (faces, mouths, clothes) is then the original.

    python3 tools/vr_band.py <orig15.mkv> <outpainted.mp4> <out.mkv> [feather_px]
"""
import subprocess
import sys

import cv2
import numpy as np

VW, VH = 1080, 1920
BAND_H = VW * 1080 / 1920        # 607.5
BAND_Y = (VH - BAND_H) / 2       # 656.25


def frames(path, w, h):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)


def main():
    orig, outp, out = sys.argv[1:4]
    fe = int(sys.argv[4]) if len(sys.argv) > 4 else 14
    # alpha for the original: 1 inside the band, ramping to 0 over `fe` px at its top and bottom edges (inside the band)
    y = np.arange(VH, dtype=np.float32) + 0.5
    a = np.clip(np.minimum(y - BAND_Y, BAND_Y + BAND_H - y) / fe, 0, 1)
    a = (a * a * (3 - 2 * a))[:, None, None]
    # the original resized to 1080 x 607.5, placed at y = 656.25 (sub-pixel shift via warpAffine)
    M = np.float32([[VW / 1920, 0, 0], [0, BAND_H / 1080, BAND_Y]])
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}",
                            "-r", "24000/1001", "-i", "-", "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    n = 0
    for o, g in zip(frames(orig, 1920, 1080), frames(outp, VW, VH)):
        ob = cv2.warpAffine(o, M, (VW, VH), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_CONSTANT)
        f = g.astype(np.float32) * (1 - a) + ob.astype(np.float32) * a
        enc.stdin.write(np.clip(f + 0.5, 0, 255).astype(np.uint8).tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    print("wrote", out, n, "frames")


if __name__ == "__main__":
    main()
