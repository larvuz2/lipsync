"""Render the animated-version section: 3 s live action, then a right-to-left gold "filter" wipe into the animated
version; the two character sheets shown as cards before and during the wipe; labels and logo; original audio.

    python3 tools/anim_render.py <orig.mkv> <animated (same frame count)> <audio.wav> <out.mp4> [crf] [debug frames]
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from melody_labels import CREAM, GOLD, INK, fonts  # noqa: E402
from pp_labels import label  # noqa: E402

W, H = 1920, 1080
FPS = 24000 / 1001
T_WIPE = (3.0, 4.35)          # line from the right edge to the left edge
T_CARDS = (1.6, 4.4, 4.9)     # cards in, start out, gone
FONTS = "work/melody/fonts"
XX = np.arange(W, dtype=np.float32)[None, :].repeat(H, 0)


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


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
    im.putalpha(Image.fromarray((np.asarray(im.getchannel("A"), np.float32) * max(a, 0)).astype(np.uint8)))
    return im


def card(path, tag, mono, w=380):
    sheet = Image.open(path).convert("RGB")
    h = round(w * sheet.height / sheet.width)
    sheet = sheet.resize((w, h), Image.LANCZOS)
    pad, bw, m = 8, 3, 30
    t = pill(tag, mono, GOLD)
    cw, ch = w + 2 * pad, h + 2 * pad
    im = Image.new("RGBA", (cw + 2 * m, ch + t.height + 8 + 2 * m), (0, 0, 0, 0))
    sh = Image.new("L", im.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle((m + 4, m + t.height + 8 + 10, m + cw + 4, m + t.height + 8 + ch + 10), 16, fill=150)
    im.paste(Image.new("RGBA", im.size, (0, 0, 0, 255)), (0, 0), sh.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im)
    y0 = m + t.height + 8
    d.rounded_rectangle((m, y0, m + cw - 1, y0 + ch - 1), 16, fill=GOLD + (255,))
    d.rounded_rectangle((m + bw, y0 + bw, m + cw - 1 - bw, y0 + ch - 1 - bw), 13, fill=(235, 235, 235, 255))
    msk = Image.new("L", sheet.size, 0)
    ImageDraw.Draw(msk).rounded_rectangle((0, 0, w - 1, h - 1), 10, fill=255)
    im.paste(sheet, (m + pad, y0 + pad), msk)
    im.alpha_composite(t, (m + 6, m))
    return im


def frames(path):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)


def main():
    orig, anim, audio, out = sys.argv[1:5]
    crf = sys.argv[5] if len(sys.argv) > 5 else "14"
    only = set(int(x) for x in sys.argv[6].split(",")) if len(sys.argv) > 6 else None
    F = fonts(FONTS)
    lb0 = label("ORIGINAL FOOTAGE", "Animated version", "live action", F)
    la0 = label("AI ANIMATION STYLE", "Animated version", "3D animated", F)
    Wl = max(lb0.width, la0.width)
    lb = label("ORIGINAL FOOTAGE", "Animated version", "live action", F, W=Wl)
    la = label("AI ANIMATION STYLE", "Animated version", "3D animated", F, W=Wl)
    br = Image.open("work/pp/labels/brand.png")
    mono = ImageFont.truetype(f"{FONTS}/SpaceMono-Bold.ttf", 17)
    tag_f = ImageFont.truetype(f"{FONTS}/SpaceMono-Bold.ttf", 19)
    c1 = card("work/anim/sheets/melody_0.png", "CHARACTER SHEET", mono)
    c2 = card("work/anim/sheets/layla_0.png", "CHARACTER SHEET", mono)
    t_live, t_anim = pill("LIVE ACTION", tag_f, CREAM), pill("ANIMATED", tag_f, GOLD)
    enc = None
    if only is None:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", "24000/1001", "-i", "-", "-i", audio, "-map", "0:v", "-map", "1:a",
                                "-c:v", "libx264", "-preset", "slow", "-crf", crf, "-pix_fmt", "yuv420p",
                                "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    ag = frames(anim)
    for n, o in enumerate(frames(orig)):
        a = next(ag)
        t = n / FPS
        u = ease((t - T_WIPE[0]) / (T_WIPE[1] - T_WIPE[0]))
        xline = W + 40 - u * (W + 80)                         # right edge -> left edge
        if t < T_WIPE[0]:
            img = o.astype(np.float32)
        elif xline < -30:
            img = a.astype(np.float32)
        else:
            img = np.where((XX > xline)[..., None], a, o).astype(np.float32)
            dist = XX - xline
            glow = np.exp(-(dist / 22.0) ** 2) * 0.6
            core = np.clip(2.6 - np.abs(dist) / 1.3, 0, 1)
            hot = np.clip(1.0 - np.abs(dist) / 1.2, 0, 1)
            g = np.array(GOLD, np.float32)
            img = img * (1 - glow[..., None]) + g * glow[..., None]
            img = img * (1 - core[..., None]) + g * core[..., None]
            img = img * (1 - 0.6 * hot[..., None]) + np.array(CREAM, np.float32) * (0.6 * hot[..., None])
        frame = Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8)).convert("RGBA")
        # character-sheet cards: bottom left (blonde) and bottom right (dark-haired)
        ca = ease((t - T_CARDS[0]) / 0.35) * (1 - ease((t - T_CARDS[1]) / (T_CARDS[2] - T_CARDS[1])))
        if ca > 0:
            pop = 0.85 + 0.15 * ease((t - T_CARDS[0]) / 0.35)
            for c, side in ((c1, 0), (c2, 1)):
                cc = c.resize((round(c.width * pop), round(c.height * pop)), Image.BICUBIC) if pop < 1 else c
                x = 26 if side == 0 else W - 26 - cc.width
                frame.alpha_composite(with_alpha(cc, ca), (x, H - 18 - cc.height))
        # tags riding the line
        if T_WIPE[0] <= t and -30 <= xline <= W + 30:
            y = 470
            frame.alpha_composite(t_live, (int(xline - 24 - t_live.width), y))
            frame.alpha_composite(t_anim, (int(xline + 24), y))
        f = min(max((t - T_WIPE[0]) / 0.3, 0), 1)
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
