"""Render the 15 s vertical-reframe demo (landscape 1920x1080 timeline).

0-5 s: the original landscape. 5.0-5.8 s: a gold 9:16 frame appears and the landscape shrinks into the band it
occupies inside the vertical. 5.8-6.6 s: the AI-extended picture grows out above and below that band (gold edges),
with "ORIGINAL 16:9" / "AI EXTENDED" tags; then the vertical plays centred, black at the sides. Labels top left
(Melody label design), Phatty Acid logo top right, original audio.

    python3 tools/vr_render.py <orig15.mkv> <vertical.mp4 (1080x1920, 360 frames)> <audio.wav> <out.mp4> [crf] [debug frames]
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from melody_labels import CREAM, GOLD, INK, fonts  # noqa: E402
from pp_labels import label  # noqa: E402

W, H = 1920, 1080
FPS = 24000 / 1001
VW, VH = 608, 1080                      # the vertical on the landscape canvas
VX = (W - VW) // 2                      # 656
BAND_H = VW * 1080 / 1920               # the 16:9 source inside the vertical: 608 x 342
BAND_Y = (VH - BAND_H) / 2              # 369
T_SHRINK = (5.0, 5.8)
T_GROW = (5.8, 6.6)
T_TAGS = (5.8, 8.2)
FONTS = "work/melody/fonts"


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def phase(t, a, b):
    return ease((t - a) / (b - a))


def pill(text, font, fg, alpha=200, pad=(14, 7), sp=3):
    tmp = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    tw = sum(tmp.textlength(c, font=font) + sp for c in text) - sp
    asc, desc = font.getmetrics()
    im = Image.new("RGBA", (int(tw + 2 * pad[0]), asc + desc + 2 * pad[1]), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=im.height // 2, fill=INK + (alpha,))
    x = pad[0]
    for ch in text:
        d.text((x, pad[1] - 1), ch, font=font, fill=fg + (255,))
        x += d.textlength(ch, font=font) + sp
    return im


def with_alpha(im, a):
    if a >= 1:
        return im
    im = im.copy()
    im.putalpha(Image.fromarray((np.asarray(im.getchannel("A"), np.float32) * a).astype(np.uint8)))
    return im


def frames(path, w, h):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)


def main():
    orig, vert, audio, out = sys.argv[1:5]
    crf = sys.argv[5] if len(sys.argv) > 5 else "14"
    only = set(int(x) for x in sys.argv[6].split(",")) if len(sys.argv) > 6 else None
    F = fonts(FONTS)
    lb = label("ORIGINAL FOOTAGE", "Vertical reframe", "16:9", F)
    la = label("AI REFRAME FOR SOCIAL", "Vertical reframe", "9:16", F)
    Wl = max(lb.width, la.width)
    lb, la = label("ORIGINAL FOOTAGE", "Vertical reframe", "16:9", F, W=Wl), label("AI REFRAME FOR SOCIAL", "Vertical reframe", "9:16", F, W=Wl)
    br = Image.open("work/pp/labels/brand.png")
    mono = ImageFont.truetype(f"{FONTS}/SpaceMono-Bold.ttf", 17)
    tag_o, tag_ai = pill("ORIGINAL 16:9", mono, CREAM), pill("AI EXTENDED", mono, GOLD)
    enc = None
    if only is None:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", "24000/1001", "-i", "-", "-i", audio, "-map", "0:v", "-map", "1:a",
                                "-c:v", "libx264", "-preset", "slow", "-crf", crf, "-pix_fmt", "yuv420p",
                                "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    vg = frames(vert, 1080, 1920)
    for n, o in enumerate(frames(orig, W, H)):
        v = next(vg)
        t = n / FPS
        s1, s2 = phase(t, *T_SHRINK), phase(t, *T_GROW)
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        if t < T_SHRINK[0]:
            canvas = Image.fromarray(o)
        else:
            vs = Image.fromarray(v).resize((VW, VH), Image.LANCZOS)
            # the shrinking landscape: full frame -> its band inside the vertical
            x0 = (1 - s1) * 0 + s1 * VX
            y0 = (1 - s1) * 0 + s1 * BAND_Y
            w0 = (1 - s1) * W + s1 * VW
            h0 = w0 * 9 / 16
            # AI-extended part revealed outward from the band (inside the vertical)
            if s2 > 0:
                grow = s2 * BAND_Y                                     # px revealed above and below the band
                top, bot = int(round(BAND_Y - grow)), int(round(BAND_Y + BAND_H + grow))
                canvas.paste(vs.crop((0, top, VW, bot)), (VX, top))
            if s2 < 1:
                src = Image.fromarray(o) if s1 < 1 else vs.crop((0, int(BAND_Y), VW, int(BAND_Y + BAND_H)))
                canvas.paste(src.resize((max(1, round(w0)), max(1, round(h0))), Image.LANCZOS), (round(x0), round(y0)))
            else:
                canvas.paste(vs, (VX, 0))
            canvas = canvas.convert("RGBA")
            d = ImageDraw.Draw(canvas)
            # gold 9:16 frame: appears with the shrink, thins out after the reveal
            fa = min(1.0, (t - T_SHRINK[0]) / 0.3) * (1 - phase(t, 7.4, 8.2))
            if fa > 0:
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(lay).rectangle((VX - 3, -2, VX + VW + 2, H + 1), outline=GOLD + (255,), width=3)
                canvas.alpha_composite(with_alpha(lay, fa))
            # gold edges riding the reveal, and the band outline + tags
            if 0 < s2 < 1:
                grow = s2 * BAND_Y
                for y in (BAND_Y - grow, BAND_Y + BAND_H + grow):
                    d.rectangle((VX, int(y) - 1, VX + VW, int(y) + 1), fill=GOLD + (255,))
            ta = phase(t, T_TAGS[0], T_TAGS[0] + 0.3) * (1 - phase(t, T_TAGS[1] - 0.4, T_TAGS[1]))
            if ta > 0 and s1 >= 1:
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ld = ImageDraw.Draw(lay)
                by0, by1 = int(BAND_Y), int(BAND_Y + BAND_H)
                for x in range(VX, VX + VW, 18):                   # dashed outline of the original band
                    ld.line((x, by0, min(x + 9, VX + VW), by0), fill=CREAM + (230,), width=2)
                    ld.line((x, by1, min(x + 9, VX + VW), by1), fill=CREAM + (230,), width=2)
                lay.alpha_composite(tag_o, (VX + (VW - tag_o.width) // 2, by0 + 12))
                lay.alpha_composite(tag_ai, (VX + (VW - tag_ai.width) // 2, max(14, int(by0 / 2 - tag_ai.height / 2))))
                lay.alpha_composite(tag_ai, (VX + (VW - tag_ai.width) // 2, int(by1 + (H - by1) / 2 - tag_ai.height / 2)))
                canvas.alpha_composite(with_alpha(lay, ta))
        frame = canvas.convert("RGBA")
        f = min(max((t - 5.0) / 0.25, 0), 1)
        if f < 1:
            frame.alpha_composite(with_alpha(lb, 1 - f), (40, 36))
        if f > 0:
            frame.alpha_composite(with_alpha(la, f), (40, 36))
        frame.alpha_composite(br, (W - 40 - br.width, 36))
        rgb = frame.convert("RGB")
        if only is not None:
            if n in only:
                rgb.save(f"{out}_{n:03d}.jpg", quality=90)
            if n >= max(only):
                break
            continue
        enc.stdin.write(rgb.tobytes())
    if enc:
        enc.stdin.close()
        enc.wait()
        print("wrote", out)


if __name__ == "__main__":
    main()
