"""Image figures for the client report (no vendor names anywhere)."""
import glob
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, "/home/user/lipsync/tools")
import analyze_clips as ac  # noqa: E402  (landmarker helper)

R = "/home/user/lipsync"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig")
MODELS = "/tmp/claude-0/-home-user-lipsync/68247ef9-9d3a-5aed-9838-8178804c0bd0/scratchpad/models"
os.makedirs(OUT, exist_ok=True)
GOLD, TEAL, WHITE, INK = (212, 162, 76), (75, 163, 168), (245, 243, 238), (17, 19, 24)
F = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
FM = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"


def font(sz, f=F):
    return ImageFont.truetype(f, sz)


def frame(clip, f, path=None):
    cap = cv2.VideoCapture(path or glob.glob(f"{R}/media/full/*Splits{clip}.mp4")[0])
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ok, img = cap.read()
    return img


def frames(path, first, n):
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    out = []
    for _ in range(n):
        ok, img = cap.read()
        if not ok:
            break
        out.append(img)
    return out


DET = cv2.FaceDetectorYN.create(f"{MODELS}/yunet.onnx", "", (1920, 1080), 0.6)


def faces(img):
    DET.setInputSize((img.shape[1], img.shape[0]))
    _, f = DET.detect(img)
    return [] if f is None else [x for x in f]


def bracket(d, x0, y0, x1, y1, col, w=4, L=None):
    L = L or int(min(x1 - x0, y1 - y0) * 0.22)
    for (ax, ay, bx, by) in [(x0, y0, x0 + L, y0), (x0, y0, x0, y0 + L), (x1, y0, x1 - L, y0), (x1, y0, x1, y0 + L),
                             (x0, y1, x0 + L, y1), (x0, y1, x0, y1 - L), (x1, y1, x1 - L, y1), (x1, y1, x1, y1 - L)]:
        d.line([(ax, ay), (bx, by)], fill=col, width=w)
    d.rectangle([x0, y0, x1, y1], outline=col + (90,), width=1)


def tag(d, x, y, text, col, sz=22, fg=INK):
    f = font(sz)
    tw = d.textlength(text, font=f)
    d.rectangle([x, y - sz - 12, x + tw + 16, y], fill=col)
    d.text((x + 8, y - sz - 8), text, font=f, fill=fg)


def pil(img):
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")


def save(im, name, q=90):
    im.convert("RGB").save(os.path.join(OUT, name), quality=q)
    print("wrote", name)


plan = json.load(open(f"{R}/exchange/full/plan.json"))


def active_pin(clip, f):
    for j in plan.get(clip, {}).get("jobs", []):
        if j["first"] <= f <= j["last"]:
            return j["face"][1:]
    return None


# ---------------------------------------------------------------- cover
img = frame("00102229", 300)
save(pil(img), "cover.jpg", 92)

# ---------------------------------------------------------------- face detection grid
picks = [("00104695", 60), ("00107025", 120), ("00103629", 50), ("00105386", 100), ("00104461", 120), ("00106229", 250)]
tiles = []
for clip, f in picks:
    img = frame(clip, f)
    im = pil(img)
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    pin = active_pin(clip, f)
    fs = faces(img)
    best = None
    if pin:
        best = min(range(len(fs)), key=lambda i: np.hypot(fs[i][0] + fs[i][2] / 2 - pin[0], fs[i][1] + fs[i][3] / 2 - pin[1])) if fs else None
    for i, fc in enumerate(fs):
        x, y, w, h = [int(v) for v in fc[:4]]
        col = GOLD if i == best else WHITE
        bracket(d, x, y, x + w, y + h, col, w=5)
        for k in range(5):
            px, py = fc[4 + 2 * k], fc[5 + 2 * k]
            d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=col + (255,))
        tag(d, x, y - 6, f"FACE {i + 1:02d} · {fc[-1] * 100:.0f}%", col, sz=26)
        if i == best:
            tag(d, x, y + h + 46, "ACTIVE SPEAKER", GOLD, sz=26)
    im = Image.alpha_composite(im, ov)
    tiles.append(im.resize((960, 540), Image.LANCZOS))
g = Image.new("RGB", (960 * 3 + 2 * 12, 540 * 2 + 12), (255, 255, 255))
for k, t in enumerate(tiles):
    g.paste(t.convert("RGB"), ((k % 3) * (960 + 12), (k // 3) * (540 + 12)))
save(g, "face_grid.jpg")

# ---------------------------------------------------------------- dense facial landmarks close-up
lm = ac.landmarker(f"{MODELS}/face_landmarker.task")
import mediapipe as mp  # noqa: E402


def mesh_on(img, box, scale=1.9):
    x, y, w, h = box
    side = max(w, h) * scale
    cx, cy = x + w / 2, y + h / 2
    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x1, y1 = int(min(img.shape[1], cx + side / 2)), int(min(img.shape[0], cy + side / 2))
    crop = img[y0:y1, x0:x1]
    up = cv2.resize(crop, (900, int(900 * crop.shape[0] / crop.shape[1])), interpolation=cv2.INTER_CUBIC)
    res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(up, cv2.COLOR_BGR2RGB)))
    return up, res


img = frame("00104461", 120)
fs = faces(img)
fc = max(fs, key=lambda f: f[2] * f[3])
up, res = mesh_on(img, [int(v) for v in fc[:4]])
im = pil(up)
ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
d = ImageDraw.Draw(ov)
W, H = im.size
LIPS = {61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 185, 40, 39, 37, 0, 267, 269, 270, 409, 78, 95, 88, 178, 87,
        14, 317, 402, 318, 324, 308, 191, 80, 81, 82, 13, 312, 311, 310, 415}
if res.face_landmarks:
    pts = res.face_landmarks[0]
    for i, p in enumerate(pts):
        px, py = p.x * W, p.y * H
        if i in LIPS:
            d.ellipse([px - 3.2, py - 3.2, px + 3.2, py + 3.2], fill=GOLD + (255,))
        else:
            d.ellipse([px - 1.6, py - 1.6, px + 1.6, py + 1.6], fill=(255, 255, 255, 150))
    a, b = pts[13], pts[14]
    l, r = pts[61], pts[291]
    d.line([(a.x * W, a.y * H - 18), (b.x * W, b.y * H + 18)], fill=TEAL + (255,), width=3)
    d.line([(l.x * W - 12, l.y * H), (r.x * W + 12, r.y * H)], fill=TEAL + (255,), width=3)
    ap = abs(a.y - b.y) / (abs(l.x - r.x) + 1e-6)
    jaw = [s.score for s in res.face_blendshapes[0] if s.category_name == "jawOpen"][0]
    tag(d, int(r.x * W) + 30, int(r.y * H) + 14, f"LIP APERTURE {ap:.2f} · JAW {jaw:.2f}", TEAL, sz=24, fg=(255, 255, 255))
    print("landmarks", len(pts))
im = Image.alpha_composite(im, ov)
save(im, "mesh.jpg")

# ---------------------------------------------------------------- two-speaker shot
img = frame("00102229", 120)
im = pil(img)
ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
d = ImageDraw.Draw(ov)
fs = faces(img)
for fc in fs:
    x, y, w, h = [int(v) for v in fc[:4]]
    left = x + w / 2 < 1000
    col = GOLD if left else TEAL
    bracket(d, x - 10, y - 10, x + w + 10, y + h + 10, col, w=6)
    tag(d, x - 10, y - 18, "PASS 1 · HUNYADI" if left else "PASS 2 · ERZSÉBET", col, sz=30,
        fg=INK if left else (255, 255, 255))
im = Image.alpha_composite(im, ov)
save(im, "two_speaker.jpg")

# ---------------------------------------------------------------- before / after mouth crops
man = {j["name"]: j for j in json.load(open(f"{R}/exchange/full/lipsync/manifest.json"))}
jobs = {j["name"]: j for j in json.load(open(f"{R}/exchange/full/lipsync_jobs.json"))}
rows = [("00104695_f0-176_s0_ac8397", "Branković"), ("00101704_f0-71", "Hunyadi"), ("00105832_f111-150_s2_997901", "Erzsébet"),
        ("00090058_f0-115", "Hunyadi's father")]
strip = []
for name, label in rows:
    j = jobs.get(name) or next(v for k, v in jobs.items() if k.startswith(name))
    out = f"{R}/exchange/full/lipsync/out/{j['name']}.mp4"
    n = j["last_frame"] - j["first_frame"] + 1
    src = frames(glob.glob(f"{R}/media/full/*Splits{j['clip']}.mp4")[0], j["first_frame"], n)
    dst = frames(out, 0, n)
    n = min(len(src), len(dst))
    fx, fy = j["face"]["xy"]
    # mouth region: track face near the pin, crop lower face
    best = []
    for k in range(0, n, 2):
        fs = faces(src[k])
        if not fs:
            continue
        fc = min(fs, key=lambda f: np.hypot(f[0] + f[2] / 2 - fx, f[1] + f[3] / 2 - fy))
        x, y, w, h = [int(v) for v in fc[:4]]
        mx, my = fc[10] / 2 + fc[12] / 2, fc[11] / 2 + fc[13] / 2  # mouth corners midpoint
        s = int(w * 0.75)
        box = (int(mx - s), int(my - s * 0.75), int(mx + s), int(my + s * 0.75))
        a = src[k][max(0, box[1]):box[3], max(0, box[0]):box[2]]
        b = dst[k][max(0, box[1]):box[3], max(0, box[0]):box[2]]
        if a.size == 0 or a.shape != b.shape:
            continue
        best.append((float(np.abs(a.astype(int) - b.astype(int)).mean()), k, a, b))
    best.sort(key=lambda t: -t[0])
    chosen = []
    for t in best:
        if all(abs(t[1] - c[1]) > n // 6 for c in chosen):
            chosen.append(t)
        if len(chosen) == 3:
            break
    chosen.sort(key=lambda t: t[1])
    row = []
    for _, k, a, b in chosen:
        row += [cv2.resize(a, (300, 225)), cv2.resize(b, (300, 225))]
    strip.append((label, row))
    print(label, [c[1] for c in chosen])
cw, ch, gap, lab = 300, 225, 8, 0
Wd = 6 * cw + 5 * gap + 2 * 14
Hd = len(strip) * (ch + gap) + 60
canvas = Image.new("RGB", (Wd, Hd), (255, 255, 255))
d = ImageDraw.Draw(canvas)
for c in range(3):
    x = c * 2 * (cw + gap) + (c * 14)
    d.text((x + 4, 14), "ORIGINAL (HUNGARIAN / SERBIAN)", font=font(17, FM), fill=(110, 110, 110))
    d.text((x + cw + gap + 4, 14), "LIP-SYNCED (ENGLISH)", font=font(17, F), fill=(170, 120, 40))
for r, (label, row) in enumerate(strip):
    y = 50 + r * (ch + gap)
    for c, t in enumerate(row):
        x = (c // 2) * 2 * (cw + gap) + (c // 2) * 14 + (c % 2) * (cw + gap)
        canvas.paste(Image.fromarray(cv2.cvtColor(t, cv2.COLOR_BGR2RGB)), (x, y))
    d.rectangle([0, y + ch - 34, d.textlength(label, font=font(20)) + 20, y + ch], fill=(17, 19, 24))
    d.text((10, y + ch - 30), label, font=font(20), fill=(245, 243, 238))
save(canvas, "lipsync_before_after.jpg")

# ---------------------------------------------------------------- change heat map (edit is confined to the speaker's lower face)
j = jobs["00103280_f102-178_s1_4d59bb"] if "00103280_f102-178_s1_4d59bb" in jobs else next(v for k, v in jobs.items() if k.startswith("00103280_f102-178"))
n = j["last_frame"] - j["first_frame"] + 1
src = frames(glob.glob(f"{R}/media/full/*Splits{j['clip']}.mp4")[0], j["first_frame"], n)
dst = frames(f"{R}/exchange/full/lipsync/out/{j['name']}.mp4", 0, n)
n = min(len(src), len(dst))
m = np.mean([np.abs(src[k].astype(np.int16) - dst[k].astype(np.int16)).mean(2) for k in range(0, n, 2)], 0)
m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 6)
m = np.clip(m / np.percentile(m, 99.7), 0, 1)
heat = cv2.applyColorMap((m * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
base = src[n // 2]
gray = cv2.cvtColor(cv2.cvtColor(base, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
alpha = (m[..., None] ** 0.6) * 0.85
mix = (gray * 0.55 * (1 - alpha) + heat * alpha).astype(np.uint8)
side = np.hstack([cv2.resize(base, (960, 540)), cv2.resize(mix, (960, 540))])
im = pil(side)
d = ImageDraw.Draw(im)
tag(d, 16, 52, "ORIGINAL FRAME", WHITE, sz=24)
tag(d, 976, 52, "PIXELS CHANGED BY LIP SYNC (AVERAGE OVER THE SHOT)", GOLD, sz=24)
save(im, "change_heatmap.jpg")
