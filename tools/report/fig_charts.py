"""Cast portraits, voice waveforms and data charts for the client report (no vendor names)."""
import glob
import json
import os
import subprocess
import sys

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from PIL import Image

R = "/home/user/lipsync"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fig")
MODELS = "/tmp/claude-0/-home-user-lipsync/68247ef9-9d3a-5aed-9838-8178804c0bd0/scratchpad/models"
for f in glob.glob("/usr/share/fonts/opentype/inter/Inter-*.otf"):
    fm.fontManager.addfont(f)
plt.rcParams.update({"font.family": "Inter", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#9AA0A6", "axes.labelcolor": "#3A3F47", "xtick.color": "#5A606B",
                     "ytick.color": "#5A606B", "figure.dpi": 200})
GOLD, TEAL, INK, SLATE, RED, GREY = "#D4A24C", "#4BA3A8", "#111318", "#5B6B82", "#B5473A", "#C9CDD2"
SR = 16000
sys.path.insert(0, f"{R}/tools")


def wav(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def src(clip):
    return glob.glob(f"{R}/media/full/*Splits{clip}.mp4")[0]


def frame(clip, f):
    cap = cv2.VideoCapture(src(clip))
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    return cap.read()[1]


DET = cv2.FaceDetectorYN.create(f"{MODELS}/yunet.onnx", "", (1920, 1080), 0.5)


def faces(img):
    DET.setInputSize((img.shape[1], img.shape[0]))
    _, f = DET.detect(img)
    return [] if f is None else list(f)


# ------------------------------------------------------------------ cast portraits
CAST = [("hunyadi", "00101704", 33, (1027, 455)), ("erzsebet", "00102065", 43, (874, 352)),
        ("brankovic", "00104461", 106, (761, 537)), ("daughter", "00103280", 127, (897, 545)),
        ("father", "00090058", 81, (806, 534)), ("miklos", "00105789", 21, (771, 568)),
        ("trainer", "00088011", 200, (805, 313)), ("janko", "00090252", 11, (659, 465)),
        ("mother", "00092071", 56, (952, 478)), ("queen", "00107637", 60, (1100, 445)),
        ("noble_fur", "00107025", 60, (1310, 354)), ("lord_chain", "00105631", 47, (1226, 471)),
        ("courtier", "00107575", 40, (1035, 439)), ("guest", "00109321", 27, (469, 495)),
        ("hall_lady", "00106229", 200, (826, 322)), ("hall_lord", "00106229", 200, (1335, 320))]
for name, clip, f, pin in CAST:
    img = frame(clip, f)
    fs = faces(img)
    fc = min(fs, key=lambda q: np.hypot(q[0] + q[2] / 2 - pin[0], q[1] + q[3] / 2 - pin[1]))
    x, y, w, h = [int(v) for v in fc[:4]]
    cx, cy, side = x + w / 2, y + h * 0.55, int(max(w, h) * 2.0)
    pad = cv2.copyMakeBorder(img, 900, 900, 900, 900, cv2.BORDER_REPLICATE)
    crop = pad[int(cy - side / 2) + 900:int(cy + side / 2) + 900, int(cx - side / 2) + 900:int(cx + side / 2) + 900]
    crop = cv2.resize(crop, (480, 480), interpolation=cv2.INTER_CUBIC if side < 480 else cv2.INTER_AREA)
    cv2.imwrite(f"{OUT}/cast_{name}.jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
print("cast portraits", len(CAST))

# ------------------------------------------------------------------ dedicated voice models: waveform + pitch
import librosa  # noqa: E402
voices = {}
for ch in ["HUNYADI", "ERZSEBET", "OLDNOBLE", "DARKWOMAN", "FATHER", "MIKLOS"]:
    x = wav(f"{R}/exchange/full/fix_inputs/voice_{ch}.wav")
    f0, v, _ = librosa.pyin(x * (0.3 / (np.abs(x).max() + 1e-9)), fmin=60, fmax=450, sr=SR, frame_length=1024)
    ff = f0[~np.isnan(f0)]
    voices[ch] = {"dur": round(len(x) / SR, 1), "f0": int(np.median(ff)), "f0_lo": int(np.percentile(ff, 10)),
                  "f0_hi": int(np.percentile(ff, 90))}
    fig, ax = plt.subplots(figsize=(4.2, 0.62))
    env = np.abs(x)
    n = 900
    seg = len(env) // n
    e = np.array([env[i * seg:(i + 1) * seg].max() for i in range(n)])
    ax.fill_between(np.arange(n), -e, e, color=GOLD if ch in ("HUNYADI", "OLDNOBLE", "FATHER", "MIKLOS") else TEAL, lw=0)
    ax.axis("off")
    ax.set_xlim(0, n)
    fig.savefig(f"{OUT}/wave_{ch}.png", bbox_inches="tight", pad_inches=0.02, transparent=True)
    plt.close(fig)
json.dump(voices, open(f"{HERE}/voices.json", "w"), indent=1)
print("voices", voices)

# ------------------------------------------------------------------ speaker attribution timeline (102229 two-shot)
import analyze_clips as ac  # noqa: E402
import mediapipe as mp  # noqa: E402
lm = ac.landmarker(f"{MODELS}/face_landmarker.task")
clip, f0_, f1_ = "00102229", 20, 420
cap = cv2.VideoCapture(src(clip))
cap.set(cv2.CAP_PROP_POS_FRAMES, f0_)
apA, apB = [], []
for k in range(f0_, f1_ + 1):
    ok, img = cap.read()
    fs = faces(img)
    vals = {"A": np.nan, "B": np.nan}
    for q in fs:
        x, y, w, h = [int(v) for v in q[:4]]
        lab = "A" if x + w / 2 < 1060 else "B"
        side = max(w, h) * 1.8
        cx, cy = x + w / 2, y + h / 2
        x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        x1, y1 = int(min(1920, cx + side / 2)), int(min(1080, cy + side / 2))
        crop = cv2.resize(img[y0:y1, x0:x1], (256, 256), interpolation=cv2.INTER_CUBIC)
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
        if res.face_landmarks:
            p = res.face_landmarks[0]
            vals[lab] = abs(p[13].y - p[14].y) / (abs(p[61].x - p[291].x) + 1e-6)
    apA.append(vals["A"])
    apB.append(vals["B"])
fps = 24000 / 1001
t = np.arange(f0_, f1_ + 1) / fps


def smooth(a, k=3):
    a = np.array(a, float)
    m = np.isnan(a)
    a[m] = np.interp(np.flatnonzero(m), np.flatnonzero(~m), a[~m]) if (~m).any() else 0
    return np.convolve(a, np.ones(k) / k, mode="same")


x = wav(src(clip))
hop = int(SR / fps)
envt = np.arange(len(x) // hop) / fps
env = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) for i in range(len(x) // hop)])
env = 20 * np.log10(env + 1e-9)
keepA = [[1.1, 2.5], [9.9, 12.6], [13.5, 14.8]]
keepB = [[3.5, 4.6], [5.3, 6.8], [7.2, 9.1], [15.2, 17.3]]
fig, axs = plt.subplots(3, 1, figsize=(10, 4.6), sharex=True, gridspec_kw={"height_ratios": [1, 1, 0.8]})
for ax, ap, col, lab, keep in [(axs[0], apA, GOLD, "Hunyadi — mouth opening", keepA),
                               (axs[1], apB, TEAL, "Erzsébet — mouth opening", keepB)]:
    for a, b in keep:
        ax.axvspan(a, b, color=col, alpha=0.16, lw=0)
    ax.plot(t, smooth(ap), color=col, lw=1.6)
    ax.set_ylabel(lab, rotation=0, ha="left", va="center", labelpad=0, fontsize=10, fontweight="semibold", color=INK)
    ax.yaxis.set_label_coords(0.005, 0.86)
    ax.set_yticks([])
for a, b in keepA:
    axs[2].axvspan(a, b, color=GOLD, alpha=0.35, lw=0)
for a, b in keepB:
    axs[2].axvspan(a, b, color=TEAL, alpha=0.35, lw=0)
axs[2].plot(envt, np.maximum(env, -70), color=INK, lw=0.8)
axs[2].set_ylabel("Dialogue level", rotation=0, ha="left", va="center", fontsize=10, fontweight="semibold", color=INK)
axs[2].yaxis.set_label_coords(0.005, 0.9)
axs[2].set_yticks([])
axs[2].set_xlabel("Time in shot (seconds)")
axs[2].set_xlim(t[0], t[-1])
fig.tight_layout(h_pad=0.4)
fig.savefig(f"{OUT}/speaker_timeline.png", bbox_inches="tight")
plt.close(fig)
print("speaker timeline")

# ------------------------------------------------------------------ word-level alignment: name correction (105386)
from align import align  # noqa: E402
clip = "00105386"
o = wav(f"{R}/exchange/full/en_orig/{clip}_EN.wav")
n_ = wav(f"{R}/exchange/full/en/{clip}_EN.wav")
a, b = 4.95, 7.25
fig, axs = plt.subplots(2, 1, figsize=(10, 3.4), sharex=True)
for ax, y, text, title, hl in [(axs[0], o, "Herjibet Szilagyi is my betrothed", "Before — machine dub mispronounces the name", 0),
                               (axs[1], n_, "Erzhebet Szilagyi is my betrothed", "After — name rebuilt in the character's cloned voice", 0)]:
    seg = y[int(a * SR):int(b * SR)]
    tt = a + np.arange(len(seg)) / SR
    ax.plot(tt, seg, color=GREY, lw=0.5)
    words = align(seg, SR, text)
    for i, (w, s, e) in enumerate(words):
        col = (RED if ax is axs[0] else GOLD) if i == hl else SLATE
        ax.axvspan(a + s - 0.02, a + e + 0.03, color=col, alpha=0.18 if i != hl else 0.35, lw=0)
        ax.text(a + (s + e) / 2, 0.92 * np.abs(seg).max(), w, ha="center", va="top", fontsize=10,
                color=INK if i != hl else (RED if ax is axs[0] else "#8A6420"), fontweight="semibold")
    ax.set_title(title, loc="left", fontsize=10.5, color=INK, fontweight="semibold")
    ax.set_yticks([])
axs[1].set_xlabel("Time in clip (seconds)")
axs[1].set_xlim(a, b)
fig.tight_layout()
fig.savefig(f"{OUT}/alignment.png", bbox_inches="tight")
plt.close(fig)
print("alignment")

# ------------------------------------------------------------------ language map of the episode
clips = json.load(open(f"{R}/exchange/full/clips.json"))
serb = {"00103835", "00104123", "00104240", "00104461", "00104695", "00107827", "00109692"}
fig, ax = plt.subplots(figsize=(10, 1.9))
x0 = 0
for c in clips:
    d = c["frames"] * 1001 / 24000
    col = RED if c["clip"] in serb else SLATE
    ax.barh(1, d, left=x0, color=col, edgecolor="white", lw=0.6, height=0.7)
    ax.barh(0, d, left=x0, color=GOLD, edgecolor="white", lw=0.6, height=0.7)
    x0 += d
ax.set_yticks([0, 1])
ax.set_yticklabels(["Delivered", "Original"], fontweight="semibold")
ax.set_xlim(0, x0)
ax.set_xlabel("Running time of the 58 clips (seconds)")
ax.spines["left"].set_visible(False)
from matplotlib.patches import Patch  # noqa: E402
ax.legend(handles=[Patch(color=SLATE, label="Hungarian dialogue"), Patch(color=RED, label="Serbian dialogue"),
                   Patch(color=GOLD, label="American English")], ncol=3, loc="upper center",
          bbox_to_anchor=(0.5, 1.42), frameon=False)
fig.tight_layout()
fig.savefig(f"{OUT}/language_map.png", bbox_inches="tight")
plt.close(fig)
print("language map")

# ------------------------------------------------------------------ frame-exact assembly timelines
plan = json.load(open(f"{R}/exchange/full/plan.json"))
nfr = {c["clip"]: c["frames"] for c in clips}
show = ["00090058", "00102229", "00103280", "00104240", "00104461", "00104695", "00105832", "00106229", "00107339", "00107827"]
labels = {"00102229": "two speakers, 2 passes", "00106229": "two speakers, 2 passes"}
fig, ax = plt.subplots(figsize=(10, 4.2))
for r, c in enumerate(show[::-1]):
    n = nfr[c]
    ax.barh(r, n, color="#E7E9EC", height=0.62)
    for j in plan[c]["jobs"]:
        ax.barh(r, j["last"] - j["first"] + 1, left=j["first"], color=GOLD if j.get("after") is None else TEAL,
                height=0.62 if j.get("after") is None else 0.3, edgecolor="white", lw=0.8)
    ax.text(n + 6, r, f"{n} frames" + (f" · {labels[c]}" if c in labels else ""), va="center", fontsize=9, color="#5A606B")
ax.set_yticks(range(len(show)))
ax.set_yticklabels([f"Clip {c[3:]}" for c in show[::-1]], fontsize=9.5)
ax.set_xlabel("Frame number")
ax.set_xlim(0, 640)
ax.legend(handles=[Patch(color="#E7E9EC", label="Original frames, untouched"), Patch(color=GOLD, label="Lip-synced (speaker 1)"),
                   Patch(color=TEAL, label="Lip-synced (speaker 2)")], ncol=3, loc="upper center",
          bbox_to_anchor=(0.45, 1.12), frameon=False, fontsize=9.5)
fig.tight_layout()
fig.savefig(f"{OUT}/assembly.png", bbox_inches="tight")
plt.close(fig)
print("assembly")

# ------------------------------------------------------------------ verification: A/V alignment per clip
ver = json.load(open(f"{R}/outputs/full/verify.json"))
fig, ax = plt.subplots(figsize=(10, 2.6))
xs = np.arange(len(ver))
ax.axhspan(-41.7, 41.7, color=GOLD, alpha=0.12, lw=0)
ax.axhline(0, color=GREY, lw=0.8)
ax.scatter(xs, [v["av_diff_ms"] for v in ver], s=22, color=INK, zorder=3)
ax.text(len(ver) - 0.5, 36, "± 1 frame", ha="right", va="top", color="#8A6420", fontsize=9, fontweight="semibold")
ax.set_ylim(-60, 60)
ax.set_xlim(-1, len(ver))
ax.set_xticks([0, 14, 29, 44, 57])
ax.set_xticklabels(["Clip 1", "15", "30", "45", "58"])
ax.set_ylabel("Audio vs picture (ms)")
fig.tight_layout()
fig.savefig(f"{OUT}/qa_av.png", bbox_inches="tight")
plt.close(fig)
print("qa")
