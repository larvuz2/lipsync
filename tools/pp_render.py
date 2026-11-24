"""Render the 13 s product-placement clip: original first 5 s, then the jacket-swapped picture, with the
product card dropped onto his jacket and a gold diagonal wipe (lower-left corner -> upper-right corner)
revealing the new jacket. Labels: top-left product-placement label (before/after), Phatty Acid logo top right.
Audio: the original clip's audio, untouched.

    python3 tools/pp_render.py <orig13.mkv> <swap8.mkv> <audio.wav> <out.mp4> [crf]
"""
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 24000 / 1001
SWITCH = 120                      # first swapped frame (5.005 s)
SHOT_IN = 113                     # cut into the close shot (4.71 s): the card drops in here
WIPE_START = 121                  # wipe from frame 121 ...
GOLD = (212, 167, 98)
CREAM = (245, 240, 230)
INK = (10, 10, 10)
FONTS = "work/melody/fonts"
JACKET = "work/pp/jacket.png"
CARD_C = (640, 745)               # card centre, over his chest in the close shot
LABEL_XY = (40, 36)


def ease_io(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def wipe_pos(n):
    """Wipe front in diagonal units s (0 = lower-left corner, 1 = upper-right corner); fast in, slow across
    his jacket (s 0.18-0.50), fast out."""
    t = (n - WIPE_START) / FPS
    if t <= 0:
        return -0.05
    keys = [(0.0, -0.05), (0.30, 0.16), (1.40, 0.50), (1.80, 1.08)]   # (seconds, s)
    for (t0, s0), (t1, s1) in zip(keys, keys[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            # ease only at the very start and end; linear (steady) across the jacket
            if t0 == 0.0:
                u = 1 - (1 - u) ** 2 * 0.6 - (1 - u) * 0.4 * (1 - u)  # gentle ease-out
            elif t1 == keys[-1][0]:
                u = u * u
            return s0 + (s1 - s0) * u
    return 2.0


YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
S = (XX / W + (H - YY) / H) / 2          # 0 at lower-left corner, 1 at upper-right corner
NORM = np.hypot(1 / W, 1 / H) / 2        # ds per pixel along the normal -> pixel distance = (S - p) / NORM


def spaced(d, xy, text, font, fill, sp):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + sp


def pill(text, font, fg, bg_alpha=190, pad=(14, 7), sp=3):
    tmp = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    tw = sum(tmp.textlength(c, font=font) + sp for c in text) - sp
    asc, desc = font.getmetrics()
    im = Image.new("RGBA", (int(tw + 2 * pad[0]), asc + desc + 2 * pad[1]), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=im.height // 2, fill=INK + (bg_alpha,))
    spaced(d, (pad[0], pad[1] - 1), text, font, fg + (255,), sp)
    return im


def make_card():
    mono = ImageFont.truetype(f"{FONTS}/SpaceMono-Bold.ttf", 17)
    jk = Image.open(JACKET).convert("RGB")
    side = 300
    jk = jk.resize((side, side), Image.LANCZOS)
    pad, bw = 12, 3
    cw = side + 2 * pad
    margin = 40
    tag = pill("THE PRODUCT", mono, GOLD)
    th = tag.height + 10
    card = Image.new("RGBA", (cw + 2 * margin, cw + th + 2 * margin), (0, 0, 0, 0))
    # shadow
    sh = Image.new("L", card.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle((margin + 6, th + margin + 12, margin + cw + 6, th + margin + cw + 12), 22, fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(16))
    card.paste(Image.new("RGBA", card.size, (0, 0, 0, 255)), (0, 0), sh)
    d = ImageDraw.Draw(card)
    x0, y0 = margin, th + margin
    d.rounded_rectangle((x0, y0, x0 + cw - 1, y0 + cw - 1), 22, fill=GOLD + (255,))
    d.rounded_rectangle((x0 + bw, y0 + bw, x0 + cw - 1 - bw, y0 + cw - 1 - bw), 19, fill=(255, 255, 255, 255))
    m = Image.new("L", jk.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, side - 1, side - 1), 12, fill=255)
    card.paste(jk, (x0 + pad, y0 + pad), m)
    card.alpha_composite(tag, (margin + (cw - tag.width) // 2, margin - 2))
    return card


def card_layer(card, n):
    """RGBA full-frame layer with the card (pop-in from SHOT_IN), or None."""
    if n < SHOT_IN:
        return None
    u = (n - SHOT_IN) / 7.0
    if u < 1:
        k = 1.70158
        e = 1 + (k + 1) * (u - 1) ** 3 + k * (u - 1) ** 2          # ease-out-back
        sc, a = 0.6 + 0.4 * e, min(1.0, u * 1.6)
    else:
        sc, a = 1.0, 1.0
    c = card if sc == 1.0 else card.resize((max(1, round(card.width * sc)), max(1, round(card.height * sc))), Image.BICUBIC)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lay.alpha_composite(c, (CARD_C[0] - c.width // 2, CARD_C[1] - c.height // 2 - 18))
    if a < 1:
        al = np.asarray(lay.getchannel("A"), np.float32) * a
        lay.putalpha(Image.fromarray(al.astype(np.uint8)))
    return lay


def over(base, lay):
    """base float32 HxWx3 (0-255), lay RGBA PIL -> composite."""
    L = np.asarray(lay, np.float32)
    a = L[..., 3:4] / 255.0
    return base * (1 - a) + L[..., :3] * a


def line_and_tags(img, p, fonts_):
    """Gold wipe line at front p, soft glow, and BEFORE / AFTER tags riding along it."""
    dist = (S - p) / NORM                                   # signed pixel distance (+ = before side)
    glow = np.exp(-(dist / 20.0) ** 2) * 0.6
    core = np.clip(2.6 - np.abs(dist) / 1.3, 0, 1)
    hot = np.clip(1.0 - np.abs(dist) / 1.2, 0, 1)
    g = np.array(GOLD, np.float32)
    img = img * (1 - glow[..., None]) + g * glow[..., None]
    img = img * (1 - core[..., None]) + g * core[..., None]
    img = img * (1 - hot[..., None] * 0.6) + np.array(CREAM, np.float32) * (hot[..., None] * 0.6)
    # tags: centred on the point of the line at y = 930 (or clamped into frame), offset either side
    y = 930.0
    x = W * (2 * p - (H - y) / H)
    if x > W - 120:
        x = W - 120.0
        y = H - H * (2 * p - x / W)
    if x < 120:
        x = 120.0
        y = H - H * (2 * p - x / W)
    nx, ny = (1 / W), (-1 / H)
    nn = np.hypot(nx, ny)
    nx, ny = nx / nn, ny / nn                                # unit normal toward the before side
    tb = pill("BEFORE", fonts_, CREAM)
    ta = pill("AFTER", fonts_, GOLD)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    off = 78
    for t, sgn in ((tb, 1), (ta, -1)):
        cx, cy = x + sgn * nx * off, y + sgn * ny * off
        lay.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))
    return over(img, lay)


def frames(path):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)


def main():
    orig, swap, audio, out = sys.argv[1:5]
    crf = sys.argv[5] if len(sys.argv) > 5 else "14"
    only = None
    if len(sys.argv) > 6:  # debug: comma list of frames to dump as jpg instead of encoding
        only = set(int(x) for x in sys.argv[6].split(","))
    mono = ImageFont.truetype(f"{FONTS}/SpaceMono-Bold.ttf", 19)
    card = make_card()
    lb = Image.open("work/pp/labels/pp_before.png")
    la = Image.open("work/pp/labels/pp_after.png")
    br = Image.open("work/pp/labels/brand.png")
    enc = None
    if only is None:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", "24000/1001", "-i", "-", "-i", audio, "-map", "0:v", "-map", "1:a",
                                "-c:v", "libx264", "-preset", "slow", "-crf", crf, "-pix_fmt", "yuv420p",
                                "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart", out],
                               stdin=subprocess.PIPE)
    sw = frames(swap)
    for n, a in enumerate(frames(orig)):
        A = a.astype(np.float32)
        B = next(sw).astype(np.float32) if n >= SWITCH else None
        cl = card_layer(card, n)
        before = over(A, cl) if cl is not None else A
        p = wipe_pos(n)
        if B is None or p < -0.02:
            img = before
        elif p > 1.06:
            img = B
        else:
            m = (S < p)[..., None]
            img = np.where(m, B, before)
            img = line_and_tags(img, p, mono)
        # labels: crossfade before -> after at 5.0-5.25 s
        t = n / FPS
        f = min(max((t - 5.0) / 0.25, 0), 1)
        frame = Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8)).convert("RGBA")
        if f < 1:
            l = lb.copy()
            if f > 0:
                l.putalpha(Image.fromarray((np.asarray(l.getchannel("A"), np.float32) * (1 - f)).astype(np.uint8)))
            frame.alpha_composite(l, LABEL_XY)
        if f > 0:
            l = la.copy()
            if f < 1:
                l.putalpha(Image.fromarray((np.asarray(l.getchannel("A"), np.float32) * f).astype(np.uint8)))
            frame.alpha_composite(l, LABEL_XY)
        frame.alpha_composite(br, (W - 40 - br.width, 36))
        rgb = frame.convert("RGB")
        if only is not None:
            if n in only:
                rgb.save(f"{out}_{n:03d}.jpg", quality=90)
            if n > max(only):
                break
            continue
        enc.stdin.write(rgb.tobytes())
    if enc:
        enc.stdin.close()
        enc.wait()
        print("wrote", out)


if __name__ == "__main__":
    main()
