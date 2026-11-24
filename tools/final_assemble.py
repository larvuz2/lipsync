"""Stitch the three Melody EP101 demos into one video, each introduced by a 3 s title card.

    python3 tools/final_assemble.py <out.mp4> [crf] [--preview frame,frame,...]

Order: title "Dubbing & Lip Sync" -> multi-language demo (ES/EN/HE/PT/FR master) -> title "Product Placement" ->
product placement v2 -> title "Vertical Reframe" -> vertical reframe demo.
Title cards: black, centred logo, "01 / 03" eyebrow, the service name large, a gold rule and one line on what follows,
in the label design (Space Mono gold, Playfair Display cream, Inter muted); the elements fade/rise in.
Transitions: each title crossfades into its clip (0.58 s) while the clip's sound fades in from silence; each clip
dips to black (0.5 s) with its sound fading out before the next title. Clip pictures and sound are otherwise untouched.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from melody_labels import CREAM, GOLD, MUTED  # noqa: E402

W, H = 1920, 1080
FPS = 24000 / 1001
SPF = 2002                    # audio samples (48 kHz) per video frame
T_FR = 72                     # title card length: 3.003 s
XF = 14                       # title -> clip crossfade / sound fade-in (0.584 s)
OUT_FR = 12                   # clip -> black dip / sound fade-out (0.5 s)
END_FR = 18                   # last clip's fade to black
FONTS = "work/melody/fonts"
CLIPS = [
    ("01 / 03", "Dubbing & Lip Sync",
     "Spanish original, then English, Hebrew, Portuguese and French in the actresses’ own voices",
     "outputs/melody/Melody_EP101_multilanguage_demo.mp4"),
    ("02 / 03", "Product Placement",
     "A brand’s jacket placed on a character after the shoot",
     "outputs/pp/Melody_EP101_product_placement_v2.mp4"),
    ("03 / 03", "Vertical Reframe",
     "A 16:9 scene extended to 9:16 for social, the original picture intact",
     "outputs/vr/Melody_EP101_vertical_reframe_demo.mp4"),
]


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** 3


class Title:
    def __init__(self, eyebrow, name, sub):
        f = lambda n, s: ImageFont.truetype(os.path.join(FONTS, n), s)
        self.mono, self.big, self.sub_f = f("SpaceMono-Bold.ttf", 24), f("PlayfairDisplay-Bold.ttf", 116), f("Inter-SemiBold.ttf", 33)
        logo = Image.open(os.path.join(FONTS, "logo_cream.png")).convert("RGBA")
        lh = 118
        self.logo = logo.resize((round(logo.width * lh / logo.height), lh), Image.LANCZOS)
        self.eyebrow, self.name, self.sub = eyebrow, name, sub
        tmp = ImageDraw.Draw(Image.new("RGB", (4, 4)))
        self.eb_w = sum(tmp.textlength(c, font=self.mono) + 7 for c in eyebrow) - 7
        self.nb = tmp.textbbox((0, 0), name, font=self.big)
        self.sb = tmp.textbbox((0, 0), sub, font=self.sub_f)
        # vertical layout, centred as a block
        self.h_logo, self.gap1, self.h_eb, self.gap2 = lh, 58, 30, 22
        self.h_name = self.nb[3] - self.nb[1]
        self.gap3, self.gap4, self.h_sub = 34, 30, self.sb[3] - self.sb[1]
        total = self.h_logo + self.gap1 + self.h_eb + self.gap2 + self.h_name + self.gap3 + 3 + self.gap4 + self.h_sub
        self.y0 = (H - total) // 2

    def frame(self, t):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        def layer(a, rise, draw_fn):
            if a <= 0:
                return
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw_fn(lay, round((1 - a) * rise))
            if a < 1:
                al = np.asarray(lay.getchannel("A"), np.float32) * a
                lay.putalpha(Image.fromarray(al.astype(np.uint8)))
            im.alpha_composite(lay)
        y = self.y0
        yl = y
        layer(ease(t / 0.5), 10, lambda L, r: L.alpha_composite(self.logo, ((W - self.logo.width) // 2, yl + r)))
        y += self.h_logo + self.gap1
        ye = y
        def eb(L, r):
            d = ImageDraw.Draw(L)
            x = (W - self.eb_w) / 2
            for c in self.eyebrow:
                d.text((x, ye + r), c, font=self.mono, fill=GOLD + (255,))
                x += d.textlength(c, font=self.mono) + 7
        layer(ease((t - 0.15) / 0.5), 14, eb)
        y += self.h_eb + self.gap2
        yn = y
        layer(ease((t - 0.25) / 0.6), 22, lambda L, r: ImageDraw.Draw(L).text(
            ((W - (self.nb[2] - self.nb[0])) / 2 - self.nb[0], yn - self.nb[1] + r), self.name, font=self.big, fill=CREAM + (255,)))
        y += self.h_name + self.gap3
        yr = y
        g = ease((t - 0.45) / 0.55)
        if g > 0:
            ImageDraw.Draw(im).rectangle(((W - 160 * g) / 2, yr, (W + 160 * g) / 2, yr + 2), fill=GOLD + (255,))
        y += 3 + self.gap4
        ys = y
        layer(ease((t - 0.55) / 0.6), 12, lambda L, r: ImageDraw.Draw(L).text(
            ((W - (self.sb[2] - self.sb[0])) / 2 - self.sb[0], ys - self.sb[1] + r), self.sub, font=self.sub_f, fill=MUTED + (255,)))
        return np.asarray(im.convert("RGB"))


def video_frames(path):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)


def audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", "48000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)


def count(path):
    s = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return int(s.strip())


def main():
    out = sys.argv[1]
    crf = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "14"
    preview = None
    if "--preview" in sys.argv:
        preview = set(int(x) for x in sys.argv[sys.argv.index("--preview") + 1].split(","))
    # timeline
    plan, pos = [], 0
    for k, (eb, name, sub, path) in enumerate(CLIPS):
        n = count(path)
        t0 = pos
        c0 = t0 + T_FR - XF                      # clip's first frame on the timeline
        last = k == len(CLIPS) - 1
        plan.append((Title(eb, name, sub), path, n, t0, c0, END_FR if last else OUT_FR))
        pos = c0 + n
    total = pos
    print("total frames", total, f"({total / FPS:.2f} s)")
    # audio track
    mix = np.zeros((total * SPF, 2), np.float32)
    for title, path, n, t0, c0, fo in plan:
        a = audio(path)[: n * SPF]
        g = np.ones(len(a), np.float32)
        fi = XF * SPF
        g[:fi] = np.sin(np.linspace(0, np.pi / 2, fi)) ** 2          # gentle fade-in under the crossfade
        fo_s = fo * SPF
        g[-fo_s:] *= np.cos(np.linspace(0, np.pi / 2, fo_s)) ** 2      # fade-out with the dip to black
        mix[c0 * SPF: c0 * SPF + len(a)] += a * g[:, None]
    audio_path = out + ".f32"
    mix.tofile(audio_path)
    enc = None
    if preview is None:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", "24000/1001", "-i", "-", "-f", "f32le", "-ar", "48000", "-ac", "2", "-i", audio_path,
                                "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", crf,
                                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", out],
                               stdin=subprocess.PIPE)
    g = 0
    def emit(fr):
        nonlocal g
        if preview is not None:
            if g in preview:
                Image.fromarray(fr).save(f"{out}_{g:04d}.jpg", quality=90)
        else:
            enc.stdin.write(np.ascontiguousarray(fr).tobytes())
        g += 1
    for title, path, n, t0, c0, fo in plan:
        if preview is not None and g > max(preview):
            break
        tf = [title.frame(i / FPS) for i in range(T_FR)]
        for i in range(T_FR - XF):
            emit(tf[i])
        for j, fr in enumerate(video_frames(path)):
            if j < XF:
                u = (j + 1) / (XF + 1)
                u = u * u * (3 - 2 * u)
                fr = (tf[T_FR - XF + j].astype(np.float32) * (1 - u) + fr.astype(np.float32) * u + 0.5).astype(np.uint8)
            elif j >= n - fo:
                u = (n - j - 1) / fo
                fr = (fr.astype(np.float32) * (u * u * (3 - 2 * u)) + 0.5).astype(np.uint8)
            emit(fr)
            if preview is not None and g > max(preview):
                break
    if enc:
        enc.stdin.close()
        enc.wait()
        print("wrote", out)
    os.remove(audio_path)


if __name__ == "__main__":
    main()
