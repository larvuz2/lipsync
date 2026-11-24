"""Masked, speech-gated assembly: the picture is the original everywhere except a soft area around each
speaker's mouth and jaw, and only while that speaker is talking (with short fades in and out).

    python3 tools/assemble_masked.py exchange/full media/full outputs/full <clip> [...]

For each lip-sync job of the clip (lipsync_jobs.json + manifest.json):
- the speaker's face is tracked on the original frames (face detection, starting from the job's pin);
- a feathered lower-face mask is built per frame from face landmarks (jaw, chin, mouth) on the original and
  the lip-synced frame, so it covers the mouth and jaw and not the background beside the face;
- a temporal envelope is built from the speech in the job's own audio (plan "en_keep"/"keep" as fallback),
  widened by PRE/POST seconds and faded over FADE frames;
- out = original * (1 - a) + lip-synced * a, with a = envelope * mask.
Writes outputs/full/<original name>_EN.mp4 (English dialogue track from exchange/full/en/<clip>_EN.wav).
"""
import glob
import json
import re
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
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
        "-r", "24000/1001"]


def frames_yuv(path):
    """Frames as planar YUV 4:4:4 (3, H, W) uint8, decoded by ffmpeg with no colour-matrix conversion,
    so blending and re-encoding keep the original colours exactly (an RGB round trip shifted dark scenes)."""
    ww, hh = (int(v) for v in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                               "stream=width,height", "-of", "csv=p=0", path],
                                              capture_output=True, text=True).stdout.strip().split(","))
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "yuv444p", "-"],
                         stdout=subprocess.PIPE)
    n = ww * hh * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            p.stdout.close()
            p.wait()
            return
        yield np.frombuffer(buf, np.uint8).reshape(3, hh, ww)


def unzoom_yuv(orig, syn, zoom, k):
    """YUV version of unzoom: the enlarged crop shrunk back into place over the original frame."""
    if not zoom:
        return syn
    zx, zy, zs = zoom_at(zoom, k)
    f = orig.copy()
    for c in range(3):
        f[c, zy:zy + zs, zx:zx + zs] = cv2.resize(syn[c], (zs, zs), interpolation=cv2.INTER_AREA)
    return f


def frames(path):
    cap = cv2.VideoCapture(path)
    while True:
        ok, im = cap.read()
        if not ok:
            return
        yield im


def zoom_at(zoom, k):
    """(zx, zy, zs) of a job's zoom window at absolute frame k (fixed window, or per-frame windows)."""
    if isinstance(zoom, dict):
        zx, zy = zoom["windows"][k - zoom["first"]]
        return zx, zy, zoom["size"]
    return zoom


def unzoom(orig, syn, zoom, k=None):
    """Full frame from a lip-synced enlarged crop: the crop shrunk back into place over the original frame."""
    if not zoom:
        return syn
    zx, zy, zs = zoom_at(zoom, k)
    f = orig.copy()
    f[zy:zy + zs, zx:zx + zs] = cv2.resize(syn, (zs, zs), interpolation=cv2.INTER_AREA)
    return f


def track(src, f0, f1, pin_frame, pin_xy, det, size=None, max_gap=12):
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
        if prev and nxt and nxt[0] - prev[-1] <= max_gap:
            a, b = prev[-1], nxt[0]
            t = (k - a) / (b - a)
            full[k] = boxes[a] * (1 - t) + boxes[b] * t
        elif (prev and not nxt and k - prev[-1] <= 4) or (nxt and not prev and nxt[0] - k <= 4):
            full[k] = boxes[prev[-1] if prev else nxt[0]]  # hold for a few frames at the ends of the track
    return full


# lower-face outline (face-mesh indices): jaw contour from one ear to the other through the chin, plus the
# mouth corners and the point under the nose, so the hull hugs the skin of the lower face
JAW = [234, 93, 132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361, 323, 454,
       2, 61, 291, 0, 17]
# mouth-only outline: outer lips, the mouth corners and the strip from the lower lip down to the chin
# (for "mask": "mouth" - keeps cheeks, beard sides and moustache edges original)
MOUTH = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185,
         57, 287, 43, 273, 204, 424, 194, 418, 200, 199, 175, 152, 148, 377]
# lips only: the outer lip contour (no chin) - the lower beard and chin stay original ("mask": "lips")
LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
_LM = None


def landmarker():
    global _LM
    if _LM is None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        _LM = (mp, vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=f"{MODELS}/face_landmarker.task"),
            running_mode=vision.RunningMode.IMAGE, num_faces=1, min_face_detection_confidence=0.3)))
    return _LM


def lower_face(im, box, idx=None):
    """Lower-face (or mouth, with idx=MOUTH) outline points (full-frame coords) of the face in box, or None."""
    idx = idx or JAW
    mp, lm = landmarker()
    x, y, w, h = box
    side = max(w, h) * 1.8
    cx, cy = x + w / 2, y + h / 2
    hh, ww = im.shape[:2]
    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x1, y1 = int(min(ww, cx + side / 2)), int(min(hh, cy + side / 2))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    crop = cv2.resize(im[y0:y1, x0:x1], (384, 384), interpolation=cv2.INTER_CUBIC)
    res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
    if not res.face_landmarks:
        return None
    q = res.face_landmarks[0]
    return np.array([[x0 + q[i].x * (x1 - x0), y0 + q[i].y * (y1 - y0)] for i in idx], np.float32)


def hull_mask(pts, w, grow=0.025, soft=0.02):
    """Filled hull of the outline points, grown a little (jaw movement) and softly feathered."""
    m = np.zeros((H, W), np.float32)
    cv2.fillConvexPoly(m, cv2.convexHull(pts.astype(np.int32)), 1.0)
    r = max(2, int(w * grow))
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    return cv2.GaussianBlur(m, (0, 0), max(1.0, w * soft))


def change_mask(orig_y, syn_y, box, w, grow, soft, thr=7.0):
    """Mask of where the lip-synced frame differs from the original near the face (luma), largest region only;
    None if nothing clear. Used when no mouth outline can be found (profile)."""
    x, y, bw, bh = box
    cx, cy = x + bw / 2, y + bh / 2
    s_ = max(bw, bh) * 1.1
    x0, y0 = int(max(0, cx - s_)), int(max(0, cy - s_ * 0.8))
    x1, y1 = int(min(W, cx + s_)), int(min(H, cy + s_ * 1.3))
    d = np.abs(syn_y[y0:y1, x0:x1].astype(np.float32) - orig_y[y0:y1, x0:x1].astype(np.float32))
    d = cv2.GaussianBlur(d, (0, 0), max(1.5, w * 0.012))
    on = (d > thr).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(on, 8)
    if n < 2:
        return None
    big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    if st[big, cv2.CC_STAT_AREA] < (w * 0.08) ** 2:
        return None
    m = np.zeros((H, W), np.float32)
    m[y0:y1, x0:x1] = (lab == big).astype(np.float32)
    r = max(2, int(w * grow))
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    return cv2.GaussianBlur(m, (0, 0), max(1.0, w * soft))


def corner_mask(q, box, grow=1.0, tight=False):
    """Mouth-only mask from the face detector's mouth corners (works on profiles, where the landmark model
    fails): an ellipse along the mouth line, reaching down to the chin, feathered."""
    x, y, w, h = box
    (rx, ry), (lx, ly) = q[0], q[1]
    cx, cy = (rx + lx) / 2, (ry + ly) / 2 + (0.02 if tight else 0.08) * h
    half = max(0.5 * np.hypot(lx - rx, ly - ry), 0.16 * w) + (0.05 if tight else 0.08) * w
    m = np.zeros((H, W), np.float32)
    ang = np.degrees(np.arctan2(ly - ry, lx - rx))
    cv2.ellipse(m, (int(cx), int(cy)), (int(half * grow), int((0.11 if tight else 0.22) * h * grow)), ang, 0, 360, 1.0, -1)
    return cv2.GaussianBlur(m, (0, 0), max(1.0, w * 0.04))


def detect_corners(det, im, box):
    """Mouth corners [(rx, ry), (lx, ly)] of the detection nearest box on this frame, or None."""
    det.setInputSize((im.shape[1], im.shape[0]))
    fs = det.detect(im)[1]
    if fs is None:
        return None
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    q = min(fs, key=lambda f: np.hypot(f[0] + f[2] / 2 - cx, f[1] + f[3] / 2 - cy))
    if np.hypot(q[0] + q[2] / 2 - cx, q[1] + q[3] / 2 - cy) > 0.6 * box[2]:
        return None
    return [(float(q[10]), float(q[11])), (float(q[12]), float(q[13]))]


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


DEBUG = [int(v) for v in os.environ["MASK_DEBUG"].split("-")] if os.environ.get("MASK_DEBUG") else None

MERGE = 2.5  # s: pauses shorter than this keep the lip sync on (no fade out and back in mid-sentence)


def best_center(cost, lo, hi):
    """Fade centre in [lo, hi] where the lip-synced and original mouth look most alike over the whole fade."""
    if hi < lo:
        return None
    vals = [(np.nansum(cost[max(0, c - FADE):c + FADE + 1]), c) for c in range(lo, hi + 1)]
    return min(vals)[1]


def plan_envelope(n_abs, f0, f1, spans, start_cut, end_cut, cost):
    """Alpha per frame. spans: speech [start, end] in seconds (absolute). On through each run of speech (pauses
    under MERGE s included); at a job end that is a shot cut (or the clip edge) it stays on to the cut, so there
    is no fade at all inside a single-speaker shot; any other fade sits where synced and original mouths match."""
    runs = []
    for a, b in spans:
        s_, t_ = int(np.floor((a - PRE) * FPS)), int(np.ceil((b + POST) * FPS))
        if runs and s_ - runs[-1][1] < MERGE * FPS:
            runs[-1][1] = max(runs[-1][1], t_)
        else:
            runs.append([s_, t_])
    if not runs:
        runs = [[f0, f1]]
    runs = [[max(f0, a), min(f1, b)] for a, b in runs if b >= f0 and a <= f1]
    e = np.zeros(n_abs, np.float32)
    fades = []
    for i, (s_, t_) in enumerate(runs):
        # fade in
        if i == 0 and start_cut:
            ci = None
        else:
            lo = (f0 if i == 0 else (runs[i - 1][1] + s_) // 2) + FADE
            ci = best_center(cost, lo, s_ - FADE)
            ci = ci if ci is not None else max(f0 + FADE, s_ - FADE)
        # fade out
        if i == len(runs) - 1 and end_cut:
            co = None
        else:
            hi = (f1 if i == len(runs) - 1 else (t_ + runs[i + 1][0]) // 2) - FADE
            co = best_center(cost, t_ + FADE, hi)
            co = co if co is not None else min(f1 - FADE, t_ + FADE)
        k = np.arange(n_abs, dtype=np.float32)
        rise = np.ones(n_abs, np.float32) if ci is None else np.clip((k - (ci - FADE)) / (2 * FADE), 0, 1)
        fall = np.ones(n_abs, np.float32) if co is None else np.clip(((co + FADE) - k) / (2 * FADE), 0, 1)
        if ci is None:
            rise[:f0] = 0
        if co is None:
            fall[f1 + 1:] = 0
        e = np.maximum(e, np.minimum(rise, fall))
        fades.append((ci, co))
    e[:f0] = 0
    e[f1 + 1:] = 0
    return e, fades


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
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from analyze_clips import cuts
    cutset = set(plan.get("cuts", cuts(src, FPS)))
    print(f"  shot cuts at frames {sorted(cutset)}", flush=True)
    layers = []
    use = {(p["first"], p["last"], p.get("variant")) for p in plan.get("jobs", []) if p.get("use", True)}
    jobs = [j for j in jobs if (j["first_frame"], j["last_frame"], j.get("variant")) in use]
    for j in jobs:
        m = man.get(j["name"])
        if not m or m.get("status") != "COMPLETED":
            raise SystemExit(f"{j['name']} has no completed output")
        # the job's own plan entry: its index is in the job name ("_s<k>"); two zoomed jobs on the same shot
        # (one per speaker) cannot be told apart by frames and face alone (the face is in zoom coordinates)
        mk = re.search(r"_s(\d+)z?(_|$)", j["name"])
        pk = plan.get("jobs", [])[int(mk.group(1))] if mk and int(mk.group(1)) < len(plan.get("jobs", [])) else None
        if pk is not None and pk["first"] == j["first_frame"] and pk["last"] == j["last_frame"] \
                and pk.get("variant") == j.get("variant"):
            pj = pk
        else:
            pj = next((p for p in plan.get("jobs", []) if p["first"] == j["first_frame"] and p["last"] == j["last_frame"]
                       and p.get("variant") == j.get("variant")
                       and (p["face"][1:] == j["face"]["xy"] or (p.get("zoom") and (p["zoom"] == j.get("zoom")
                                                                                     or p["zoom"] == "track")))), {})
        f0, f1 = j["first_frame"], j["last_frame"]
        # gate on the speech actually in this job's audio (falls back to the plan's windows)
        aud = os.path.join(ex, j["audio"])
        windows = [[round(a + f0 / FPS, 2), round(b + f0 / FPS, 2)] for a, b in speech_spans(aud)] \
            if os.path.exists(aud) else (pj.get("en_keep") or pj.get("keep") or [])
        if pj.get("also_windows"):
            # also cover where the ORIGINAL line moved the mouth (e.g. the dub starts later than the original):
            # there the lip-synced mouth (quiet) replaces original mouth movement that would have no sound
            ws = sorted([list(w) for w in windows] + [list(w) for w in pj["also_windows"]
                                                       if w[1] > f0 / FPS and w[0] < (f1 + 1) / FPS])
            merged = []
            for a, b in ws:
                if merged and a <= merged[-1][1] + 0.05:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            windows = [[round(max(a, f0 / FPS), 2), round(min(b, (f1 + 1) / FPS), 2)] for a, b in merged]
        if pj.get("gate") is False:
            # keep this job's mouth for its whole range (reproduces an approved full lip sync, mouths only)
            windows = [[round(f0 / FPS + PRE, 3), round(f1 / FPS - POST, 3)]]
        zoom = j.get("zoom")
        if isinstance(zoom, dict):
            zoom = {**zoom, **json.load(open(os.path.join(ex, zoom["file"])))}
        if zoom:
            zx, zy, zs = zoom_at(zoom, f0 + j["face"]["frame"])
            pin = (zx + j["face"]["xy"][0] * zs / 1080, zy + j["face"]["xy"][1] * zs / 1080)
        else:
            pin = tuple(j["face"]["xy"])
        if zoom and j.get("input_video"):
            # small face: track it on the enlarged input, where it is ~3x bigger, then map back
            zin = os.path.join(ex, j["input_video"])
            zdet = cv2.FaceDetectorYN.create(f"{MODELS}/yunet.onnx", "", (1080, 1080), 0.4)
            zb = track(zin, 0, f1 - f0, j["face"]["frame"], tuple(j["face"]["xy"]), zdet, size=(1080, 1080))
            boxes = {}
            for kk, q in zb.items():
                zx, zy, zs = zoom_at(zoom, f0 + kk)
                kz = zs / 1080
                boxes[f0 + kk] = np.array([zx + q[0] * kz, zy + q[1] * kz, q[2] * kz, q[3] * kz])
            known = sorted(boxes)
            for kk in range(f0, f1 + 1):  # any frame still missing: interpolate along the path
                if kk not in boxes and known:
                    lo_ = [q for q in known if q < kk]
                    hi_ = [q for q in known if q > kk]
                    a_, b_ = (lo_[-1] if lo_ else hi_[0]), (hi_[0] if hi_ else lo_[-1])
                    t_ = 0 if a_ == b_ else (kk - a_) / (b_ - a_)
                    boxes[kk] = boxes[a_] * (1 - t_) + boxes[b_] * t_
        elif pj.get("pins"):
            # the job spans a cut: track each shot on its own, from its own pin (frame -> [x, y])
            pins = {f0 + j["face"]["frame"]: pin, **{int(k): tuple(v) for k, v in pj["pins"].items()}}
            bounds = sorted({f0, f1 + 1, *[c for c in cutset if f0 < c <= f1]})
            boxes = {}
            det_lo = cv2.FaceDetectorYN.create(f"{MODELS}/yunet.onnx", "", (W, H), 0.25)
            for a_, b_ in zip(bounds[:-1], bounds[1:]):
                pk = [k for k in pins if a_ <= k < b_]
                if not pk:
                    raise SystemExit(f"{j['name']}: no pin for the shot {a_}-{b_ - 1}")
                boxes.update(track(src, a_, b_ - 1, pk[0], pins[pk[0]], det_lo, max_gap=int(pj.get("max_gap", 24))))
        else:
            boxes = track(src, f0, f1, f0 + j["face"]["frame"], pin, det)
            if len(boxes) < 0.97 * (f1 - f0 + 1):
                # dark or turning face: retry with a lower detection threshold, bridge gaps up to ~1 s
                det_lo = cv2.FaceDetectorYN.create(f"{MODELS}/yunet.onnx", "", (W, H), 0.25)
                b2 = track(src, f0, f1, f0 + j["face"]["frame"], pin, det_lo, max_gap=int(pj.get("max_gap", 24)))
                if len(b2) > len(boxes):
                    boxes = b2
        if pj.get("steady") and boxes:
            # very close / moving face (e.g. a close-up at a mic): the detector's box jumps in size and place from
            # frame to frame; a temporal median of centre and size keeps it on the face
            ks = sorted(boxes)
            arr = np.array([[boxes[q][0] + boxes[q][2] / 2, boxes[q][1] + boxes[q][3] / 2, boxes[q][2], boxes[q][3]]
                            for q in ks])
            r = 3
            med = np.array([np.median(arr[max(0, i - r):i + r + 1], 0) for i in range(len(ks))])
            boxes = {q: np.array([cx - w / 2, cy - h / 2, w, h]) for q, (cx, cy, w, h) in zip(ks, med)}
        # frames where the mouth can be seen (e.g. not hidden by a hand or by someone passing in front)
        a0, a1 = pj.get("active", [f0, f1])
        layers.append({"name": j["name"], "f0": f0, "f1": f1, "a0": max(f0, a0), "a1": min(f1, a1), "boxes": boxes,
                       "spans": windows, "start_cut": f0 == 0 or f0 in cutset or a0 > f0,
                       "end_cut": f1 >= n - 1 or (f1 + 1) in cutset or a1 < f1,
                       "out": os.path.join(ex, m["file"]), "it": None, "zoom": zoom,
                       "idx": {"mouth": MOUTH, "lips": LIPS}.get(pj.get("mask"), JAW),
                       "grow": {"mouth": 0.04, "lips": 0.05}.get(pj.get("mask"), 0.025),
                       "soft": {"mouth": 0.03, "lips": 0.025}.get(pj.get("mask"), 0.02),
                       "tight": pj.get("mask") == "lips",
                       "zin": os.path.join(ex, j["input_video"]) if zoom else None,
                       "steady": bool(pj.get("steady")),
                       "fade_profile": bool(pj.get("fade_profile")),
                       "wmed": float(np.median([b[2] for b in boxes.values()])) if boxes else None})
        print(f"  {j['name']}: face tracked on {len(boxes)}/{f1 - f0 + 1} frames, windows {windows or 'whole job'}",
              flush=True)
    for L in layers:
        # outline of the lower face on the original and on the lip-synced frame (the synced jaw can open wider);
        # the mask is the hull of both, so it covers the new mouth and nothing beside the face
        co, cs = cv2.VideoCapture(src), cv2.VideoCapture(L["out"])
        co.set(cv2.CAP_PROP_POS_FRAMES, L["f0"])
        cz = cv2.VideoCapture(L["zin"]) if L["zoom"] else None
        cdet = cv2.FaceDetectorYN.create(f"{MODELS}/yunet.onnx", "", (W, H), 0.3)
        L["corners"] = {}
        raw = {}
        cost = np.full(n, np.nan, np.float32)
        for k in range(L["f0"], L["f1"] + 1):
            ok1, a = co.read()
            ok2, b = cs.read()
            az = cz.read()[1] if cz is not None else None  # keep the zoom input in step with every frame
            if not (ok1 and ok2) or k not in L["boxes"]:
                continue
            if L["zoom"]:
                # small face: find the outline / mouth corners on the enlarged crops, then map them back
                zx, zy, zs = zoom_at(L["zoom"], k)
                kz = b.shape[0] / zs
                bx = L["boxes"][k]
                bz = ((bx[0] - zx) * kz, (bx[1] - zy) * kz, bx[2] * kz, bx[3] * kz)
                pa, pb = lower_face(az, bz, L["idx"]), lower_face(b, bz, L["idx"])
                pa = None if pa is None else pa / kz + np.array([zx, zy], np.float32)
                pb = None if pb is None else pb / kz + np.array([zx, zy], np.float32)
                cq = detect_corners(cdet, az, bz)
                if cq is not None:
                    L["corners"][k] = [(zx + px / kz, zy + py / kz) for px, py in cq]
                b = unzoom(a, b, L["zoom"], k)
            else:
                bk = L["boxes"][k]
                if L["steady"] and L.get("mc") is not None:
                    # follow the mouth itself (where it was on the last frame), not the detector's jumpy face box
                    wq = L["wmed"]
                    bk = np.array([L["mc"][0] - wq / 2, L["mc"][1] - 0.72 * wq * 1.1, wq, wq * 1.1])
                    L["boxes"][k] = bk
                pa, pb = lower_face(a, bk, L["idx"]), lower_face(b, bk, L["idx"])
                if L["steady"] and pa is None and pb is None and bk is not L["boxes"].get(k):
                    pa, pb = lower_face(a, L["boxes"][k], L["idx"]), lower_face(b, L["boxes"][k], L["idx"])
                cq = detect_corners(cdet, a, bk)
                if cq is not None:
                    L["corners"][k] = cq
            if L["steady"] and (pa is None) != (pb is None):
                pa = pb if pa is None else pa  # same point count on every frame, so outlines can be interpolated
                pb = pa if pb is None else pb
            if L["steady"] and pa is not None:
                L["mc"] = np.concatenate([pa, pb]).mean(0)
            if pa is not None or pb is not None:
                raw[k] = np.concatenate([p for p in (pa, pb) if p is not None])
            # how different the lip-synced mouth looks from the original on this frame
            mk = hull_mask(raw[k], L["boxes"][k][2], L["grow"], L["soft"]) if k in raw else \
                (corner_mask(L["corners"][k], L["boxes"][k], tight=L["tight"]) if k in L["corners"] else ellipse_mask(L["boxes"][k]))
            d = np.abs(a.astype(np.float32) - b.astype(np.float32)).mean(2)
            cost[k] = float((d * mk).sum() / max(mk.sum(), 1.0))
        cost = np.where(np.isnan(cost), np.nanmax(cost) if np.isfinite(cost).any() else 0, cost)
        env, fades = plan_envelope(n, L["a0"], L["a1"], L["spans"], L["start_cut"], L["end_cut"], cost)
        L["env"] = env
        print(f"  {L['name']}: speech {L['spans']}, on frames {L['a0']}-{L['a1']} "
              f"(start {'cut' if L['start_cut'] else 'fade'}, end {'cut' if L['end_cut'] else 'fade'}), "
              f"fade centres {fades}", flush=True)
        pts = {}
        for k in raw:
            # +-2 frame smoothing of the outline (same point count only), to keep the mask edge steady
            nb = [raw[j] for j in range(k - 2, k + 3) if j in raw and raw[j].shape == raw[k].shape]
            pts[k] = np.mean(nb, 0)
        L["pts"] = pts
        need = [k for k in range(L["f0"], L["f1"] + 1) if env[k] > 0 and k in L["boxes"]]
        print(f"  {L['name']}: lower-face outline on {len(pts)}/{len(need)} gated frames", flush=True)
        if L.get("steady") and L.get("fade_profile"):
            # runs of 4+ frames with no mouth outline (head in profile): no mask can be trusted there, so the lip
            # sync fades out and back in smoothly over 3 frames instead of flipping between mouths frame by frame
            miss = np.array([0.0 if k in pts else 1.0 for k in range(n)], np.float32)
            runs, k = [], 0
            while k < n:
                if miss[k] and env[k] > 0:
                    j = k
                    while j < n and miss[j] and env[j] > 0:
                        j += 1
                    if j - k >= 4:  # shorter gaps: the interpolated outline holds
                        runs.append((k, j - 1))
                    k = j
                else:
                    k += 1
            off = np.zeros(n, np.float32)
            for a_, b_ in runs:
                off[a_:b_ + 1] = 1
            kern = np.ones(7, np.float32) / 7
            fade = 1 - np.clip(np.convolve(np.maximum(off, np.convolve(off, np.ones(3), "same") > 0), kern, "same"), 0, 1)
            L["env"] = env = env * fade
            if runs:
                print(f"  {L['name']}: lip sync faded out where the mouth cannot be found (profile): "
                      f"{[(round(a_ / FPS, 2), round(b_ / FPS, 2)) for a_, b_ in runs]}", flush=True)
        # one mask type per shot, so the mask edge does not change shape from frame to frame
        gaps = [k for k in need if not any(q in pts for q in range(k - 12, k + 13))]
        if need and ((len(pts) < 0.8 * len(need) and len(L["corners"]) > len(pts))
                     or (gaps and len(L["corners"]) >= 0.95 * len(need))):
            L["pts"] = {}
            print(f"  {L['name']}: using the mouth-corner mask for the whole shot "
                  f"(corners on {len(L['corners'])}/{len(need)} frames)", flush=True)
    dst = os.path.join(out_dir, os.path.basename(src)[:-4] + "_EN.mp4")
    audio = os.path.join(ex, "en", f"{clip}_EN.wav")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv444p", "-s", f"{W}x{H}",
                            "-r", "24000/1001", "-i", "-", "-i", audio, "-map", "0:v", "-map", "1:a", *X264,
                            "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart", dst],
                           stdin=subprocess.PIPE)
    # shots kept exactly as already delivered (e.g. other speakers already done): taken from plan["base_from"]
    keep = [tuple(r) for r in plan.get("base_keep", [])]
    base_it = frames_yuv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ex))), plan["base_from"])) \
        if keep else None
    for k, im in enumerate(frames_yuv(src)):
        if base_it is not None:
            bf = next(base_it)
            if any(a <= k <= b for a, b in keep):
                im = bf
        outf = im.astype(np.float32)
        for L in layers:
            if not (L["f0"] <= k <= L["f1"]):
                continue
            if L["it"] is None:
                L["it"] = frames_yuv(L["out"])
            sy = next(L["it"])
            syn = unzoom_yuv(im, sy, L["zoom"], k) if L["zoom"] else sy
            a = L["env"][k]
            if a <= 0 or k not in L["boxes"]:
                continue
            box = L["boxes"][k]
            near = [j for j in range(k - 12, k + 13) if j in L["pts"]]
            if L["steady"] and near:
                wq = L["wmed"]
                grow = L["grow"]
                if k in L["pts"]:
                    j, P = k, L["pts"][k]
                else:
                    # no outline on this frame (e.g. the head turning to profile): the neighbours' outlines,
                    # interpolated, moved with the mouth (the detector's mouth corners; the face box is no guide when
                    # the head turns: it shrinks and moves while the mouth goes elsewhere), and the mask a little wider
                    cen = lambda q: np.mean(np.array(L["corners"][q], np.float32), 0) if q in L["corners"] else None
                    before = [q for q in near if q < k]
                    after = [q for q in near if q > k]
                    j1 = max(before) if before else None
                    j2 = min(after) if after else None
                    ck = cen(k)
                    if j1 is not None and j2 is not None and L["pts"][j1].shape == L["pts"][j2].shape:
                        u = (k - j1) / (j2 - j1)
                        j, P = j1, L["pts"][j1] * (1 - u) + L["pts"][j2] * u
                        c1, c2 = cen(j1), cen(j2)
                        ref = None if c1 is None or c2 is None else c1 * (1 - u) + c2 * u
                    else:
                        j = j1 if j1 is not None else j2
                        P, ref = L["pts"][j], cen(j)
                    if ck is not None and ref is not None:
                        P = P + (ck - ref)
                    grow = L["grow"] * 1.5
                m = hull_mask(P, wq, grow, L["soft"]) * a
                if k not in L["pts"]:
                    # in profile even the mouth corners are unreliable: take where the lip sync really changed the
                    # picture around the face (the new mouth), instead of a guessed outline
                    dm = change_mask(im[0], syn[0], box, wq, L["grow"], L["soft"])
                    if dm is not None:
                        m = dm * a
            elif near:
                j = min(near, key=lambda q: abs(q - k))
                bj = L["boxes"].get(j, box)
                shift = np.array([box[0] + box[2] / 2 - bj[0] - bj[2] / 2, box[1] + box[3] / 2 - bj[1] - bj[3] / 2])
                m = hull_mask(L["pts"][j] + shift, box[2], L["grow"], L["soft"]) * a
            else:
                nc = [j for j in range(k - 12, k + 13) if j in L["corners"]]
                if nc:
                    j = min(nc, key=lambda q: abs(q - k))
                    bj = L["boxes"].get(j, box)
                    dx, dy = box[0] + box[2] / 2 - bj[0] - bj[2] / 2, box[1] + box[3] / 2 - bj[1] - bj[3] / 2
                    m = corner_mask([(px + dx, py + dy) for px, py in L["corners"][j]], box, tight=L["tight"]) * a
                    L["corner_fb"] = L.get("corner_fb", 0) + 1
                else:
                    m = ellipse_mask(box) * a
                    L["fallback"] = L.get("fallback", 0) + 1
            if DEBUG and DEBUG[0] <= k <= DEBUG[1]:
                ys_, xs_ = np.nonzero(m > 0.5)
                cm = (int(xs_.mean()), int(ys_.mean())) if len(xs_) else None
                print(f"    debug {L['name'][-9:]} frame {k}: alpha {a:.2f} mask sum {m.sum():.0f} centre {cm} "
                      f"outline from {j if near else None} box {np.round(box[:4]).astype(int).tolist()}", flush=True)
            outf = outf * (1 - m[None]) + syn.astype(np.float32) * m[None]
        enc.stdin.write(np.clip(outf + 0.5, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    for L in layers:
        if L.get("corner_fb"):
            print(f"  {L['name']}: mouth-corner mask on {L['corner_fb']} frames (no landmark outline)", flush=True)
        if L.get("fallback"):
            print(f"  {L['name']}: ellipse fallback on {L['fallback']} frames", flush=True)
    got = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                              "stream=nb_read_frames", "-of", "csv=p=0", dst], capture_output=True, text=True).stdout)
    print(f"{clip}: {'OK' if got == n else f'FRAME MISMATCH {got}/{n}'} - masked composite of {len(layers)} lip-sync layer(s)",
          flush=True)


if __name__ == "__main__":
    ex, media, out = sys.argv[1:4]
    for c in sys.argv[4:]:
        build(ex, media, out, c)
