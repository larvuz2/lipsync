"""Masked, speech-gated assembly: the picture is the original everywhere except a soft area around each
speaker's mouth and jaw, and only while that speaker is talking (with short fades in and out).

    python3 tools/assemble_masked.py exchange/full media/full outputs/full <clip> [...]

For each lip-sync job of the clip (lipsync_jobs.json + manifest.json):
- the speaker's face is tracked on the original frames (face detection, starting from the job's pin);
- a feathered lower-face ellipse is built per frame;
- a temporal envelope is built from the speech in the job's own audio (plan "en_keep"/"keep" as fallback),
  widened by PRE/POST seconds and faded over FADE frames;
- out = original * (1 - a) + lip-synced * a, with a = envelope * mask.
Writes outputs/full/<original name>_EN.mp4 (English dialogue track from exchange/full/en/<clip>_EN.wav).
"""
import glob
import json
import os
import subprocess
import sys

import cv2
import numpy as np

W, H = 1920, 1080
FPS = 24000 / 1001
FADE = 4          # frames of fade in/out around speech windows
PRE, POST = 0.12, 0.18
MODELS = "/tmp/claude-0/-home-user-lipsync/68247ef9-9d3a-5aed-9838-8178804c0bd0/scratchpad/models"
X264 = ["-c:v", "libx264", "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-r", "24000/1001"]


def frames(path):
    cap = cv2.VideoCapture(path)
    while True:
        ok, im = cap.read()
        if not ok:
            return
        yield im


def track(src, f0, f1, pin_frame, pin_xy, det):
    """Face box per frame in [f0, f1] (absolute), following the face nearest the pin from the pin frame."""
    cap = cv2.VideoCapture(src)
    raw = {}
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
    for k in range(f0, f1 + 1):
        ok, im = cap.read()
        if not ok:
            break
        det.setInputSize((im.shape[1], im.shape[0]))
        fs = det.detect(im)[1]
        raw[k] = [] if fs is None else [q[:4].astype(float) for q in fs]

    def walk(order):
        out, (px, py), size = {}, pin_xy, None
        for k in order:
            best = None
            for q in raw.get(k, []):
                d = np.hypot(q[0] + q[2] / 2 - px, q[1] + q[3] / 2 - py)
                lim = 0.9 * (size or max(q[2], 120))
                if d < lim and (best is None or d < best[0]):
                    best = (d, q)
            if best is not None:
                q = best[1]
                px, py, size = q[0] + q[2] / 2, q[1] + q[3] / 2, max(q[2], q[3])
                out[k] = q
        return out

    pf = min(max(pin_frame, f0), f1)
    boxes = walk(range(pf, f1 + 1))
    boxes.update(walk(range(pf, f0 - 1, -1)))
    # fill short gaps by interpolation; mark long gaps as missing
    ks = sorted(boxes)
    full = {}
    for k in range(f0, f1 + 1):
        if k in boxes:
            full[k] = boxes[k]
            continue
        prev = [j for j in ks if j < k]
        nxt = [j for j in ks if j > k]
        if prev and nxt and nxt[0] - prev[-1] <= 8:
            a, b = prev[-1], nxt[0]
            t = (k - a) / (b - a)
            full[k] = boxes[a] * (1 - t) + boxes[b] * t
    return full


def ellipse_mask(box):
    x, y, w, h = box
    m = np.zeros((H, W), np.float32)
    cx, cy = int(x + w / 2), int(y + h * 0.74)
    cv2.ellipse(m, (cx, cy), (int(w * 0.6), int(h * 0.46)), 0, 0, 360, 1.0, -1)
    s = max(3, int(w * 0.1)) | 1
    return cv2.GaussianBlur(m, (0, 0), s / 2)


def envelope(n_abs, f0, f1, windows):
    e = np.zeros(n_abs, np.float32)
    if not windows:
        e[f0:f1 + 1] = 1
    else:
        for a, b in windows:
            # widened by FADE frames so the fade is finished before speech starts (full lip sync while speaking)
            s, t = int(np.floor((a - PRE) * FPS)) - FADE, int(np.ceil((b + POST) * FPS)) + FADE
            e[max(f0, s):min(f1, t) + 1] = 1
    # fades
    k = np.ones(2 * FADE + 1, np.float32) / (2 * FADE + 1)
    e = np.convolve(e, k, mode="same")
    e[:f0] = 0
    e[f1 + 1:] = 0
    return np.clip(e, 0, 1)


def speech_spans(path, gap=0.35, floor_db=-45.0):
    """Spans (s, relative to the job start) where the job's own audio has speech: what the mouth was synced to."""
    import soundfile as sf
    x, sr = sf.read(path)
    x = x.mean(1) if x.ndim > 1 else x
    w = int(sr * 0.05)
    on = 20 * np.log10(np.sqrt(np.convolve(x ** 2, np.ones(w) / w, "same")) + 1e-9) > floor_db
    spans, k = [], 0
    while k < len(on):
        if on[k]:
            m = k
            while m < len(on) and on[m]:
                m += 1
            if (m - k) / sr > 0.05:
                if spans and k / sr - spans[-1][1] < gap:
                    spans[-1][1] = m / sr
                else:
                    spans.append([k / sr, m / sr])
            k = m
        else:
            k += 1
    return spans


def build(ex, media, out_dir, clip):
    plan = json.load(open(os.path.join(ex, "plan.json"))).get(clip, {})
    jobs = [j for j in json.load(open(os.path.join(ex, "lipsync_jobs.json"))) if j["clip"] == clip]
    man = {m["name"]: m for m in json.load(open(os.path.join(ex, "lipsync", "manifest.json")))}
    src = glob.glob(os.path.join(media, f"*Splits{clip}.mp4"))[0]
    n = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", src], capture_output=True, text=True).stdout)
    det = cv2.FaceDetectorYN.create(f"{MODELS}/yunet.onnx", "", (W, H), 0.5)
    layers = []
    for j in jobs:
        m = man.get(j["name"])
        if not m or m.get("status") != "COMPLETED":
            raise SystemExit(f"{j['name']} has no completed output")
        pj = next((p for p in plan.get("jobs", []) if p["first"] == j["first_frame"] and p["last"] == j["last_frame"]
                   and p["face"][1:] == j["face"]["xy"]), {})
        f0, f1 = j["first_frame"], j["last_frame"]
        # gate on the speech actually in this job's audio (falls back to the plan's windows)
        aud = os.path.join(ex, j["audio"])
        windows = [[round(a + f0 / FPS, 2), round(b + f0 / FPS, 2)] for a, b in speech_spans(aud)] \
            if os.path.exists(aud) else (pj.get("en_keep") or pj.get("keep") or [])
        boxes = track(src, f0, f1, f0 + j["face"]["frame"], tuple(j["face"]["xy"]), det)
        layers.append({"name": j["name"], "f0": f0, "f1": f1, "boxes": boxes, "env": envelope(n, f0, f1, windows),
                       "out": os.path.join(ex, m["file"]), "it": None})
        print(f"  {j['name']}: face tracked on {len(boxes)}/{f1 - f0 + 1} frames, windows {windows or 'whole job'}",
              flush=True)
    dst = os.path.join(out_dir, os.path.basename(src)[:-4] + "_EN.mp4")
    audio = os.path.join(ex, "en", f"{clip}_EN.wav")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", "24000/1001", "-i", "-", "-i", audio, "-map", "0:v", "-map", "1:a", *X264,
                            "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart", dst],
                           stdin=subprocess.PIPE)
    for k, im in enumerate(frames(src)):
        outf = im.astype(np.float32)
        for L in layers:
            if not (L["f0"] <= k <= L["f1"]):
                continue
            if L["it"] is None:
                L["it"] = frames(L["out"])
            syn = next(L["it"])
            a = L["env"][k]
            if a <= 0 or k not in L["boxes"]:
                continue
            m = ellipse_mask(L["boxes"][k]) * a
            outf = outf * (1 - m[..., None]) + syn.astype(np.float32) * m[..., None]
        enc.stdin.write(np.clip(outf + 0.5, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    got = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                              "stream=nb_read_frames", "-of", "csv=p=0", dst], capture_output=True, text=True).stdout)
    print(f"{clip}: {'OK' if got == n else f'FRAME MISMATCH {got}/{n}'} - masked composite of {len(layers)} lip-sync layer(s)",
          flush=True)


if __name__ == "__main__":
    ex, media, out = sys.argv[1:4]
    for c in sys.argv[4:]:
        build(ex, media, out, c)
