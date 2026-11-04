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
        if prev and nxt and nxt[0] - prev[-1] <= 12:
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
    for j in jobs:
        m = man.get(j["name"])
        if not m or m.get("status") != "COMPLETED":
            raise SystemExit(f"{j['name']} has no completed output")
        pj = next((p for p in plan.get("jobs", []) if p["first"] == j["first_frame"] and p["last"] == j["last_frame"]
                   and (p["face"][1:] == j["face"]["xy"] or (p.get("zoom") and (p["zoom"] == j.get("zoom")
                                                                                 or p["zoom"] == "track")))), {})
        f0, f1 = j["first_frame"], j["last_frame"]
        # gate on the speech actually in this job's audio (falls back to the plan's windows)
        aud = os.path.join(ex, j["audio"])
        windows = [[round(a + f0 / FPS, 2), round(b + f0 / FPS, 2)] for a, b in speech_spans(aud)] \
            if os.path.exists(aud) else (pj.get("en_keep") or pj.get("keep") or [])
        zoom = j.get("zoom")
        if isinstance(zoom, dict):
            zoom = {**zoom, **json.load(open(os.path.join(ex, zoom["file"])))}
        if zoom:
            zx, zy, zs = zoom_at(zoom, f0 + j["face"]["frame"])
            pin = (zx + j["face"]["xy"][0] * zs / 1080, zy + j["face"]["xy"][1] * zs / 1080)
        else:
            pin = tuple(j["face"]["xy"])
        boxes = track(src, f0, f1, f0 + j["face"]["frame"], pin, det)
        # frames where the mouth can be seen (e.g. not hidden by a hand or by someone passing in front)
        a0, a1 = pj.get("active", [f0, f1])
        layers.append({"name": j["name"], "f0": f0, "f1": f1, "a0": max(f0, a0), "a1": min(f1, a1), "boxes": boxes,
                       "spans": windows, "start_cut": f0 == 0 or f0 in cutset or a0 > f0,
                       "end_cut": f1 >= n - 1 or (f1 + 1) in cutset or a1 < f1,
                       "out": os.path.join(ex, m["file"]), "it": None, "zoom": zoom,
                       "idx": MOUTH if pj.get("mask") == "mouth" else JAW,
                       "grow": 0.04 if pj.get("mask") == "mouth" else 0.025,
                       "soft": 0.03 if pj.get("mask") == "mouth" else 0.02,
                       "zin": os.path.join(ex, j["input_video"]) if zoom else None})
        print(f"  {j['name']}: face tracked on {len(boxes)}/{f1 - f0 + 1} frames, windows {windows or 'whole job'}",
              flush=True)
    for L in layers:
        # outline of the lower face on the original and on the lip-synced frame (the synced jaw can open wider);
        # the mask is the hull of both, so it covers the new mouth and nothing beside the face
        co, cs = cv2.VideoCapture(src), cv2.VideoCapture(L["out"])
        co.set(cv2.CAP_PROP_POS_FRAMES, L["f0"])
        cz = cv2.VideoCapture(L["zin"]) if L["zoom"] else None
        raw = {}
        cost = np.full(n, np.nan, np.float32)
        for k in range(L["f0"], L["f1"] + 1):
            ok1, a = co.read()
            ok2, b = cs.read()
            if not (ok1 and ok2) or k not in L["boxes"]:
                continue
            if L["zoom"]:
                # small face: find the lower-face outline on the enlarged crops, then map it back
                zx, zy, zs = zoom_at(L["zoom"], k)
                kz = b.shape[0] / zs
                az = cz.read()[1]
                bx = L["boxes"][k]
                bz = ((bx[0] - zx) * kz, (bx[1] - zy) * kz, bx[2] * kz, bx[3] * kz)
                pa, pb = lower_face(az, bz, L["idx"]), lower_face(b, bz, L["idx"])
                pa = None if pa is None else pa / kz + np.array([zx, zy], np.float32)
                pb = None if pb is None else pb / kz + np.array([zx, zy], np.float32)
                b = unzoom(a, b, L["zoom"], k)
            else:
                pa, pb = lower_face(a, L["boxes"][k], L["idx"]), lower_face(b, L["boxes"][k], L["idx"])
            if pa is not None or pb is not None:
                raw[k] = np.concatenate([p for p in (pa, pb) if p is not None])
            # how different the lip-synced mouth looks from the original on this frame
            mk = hull_mask(raw[k], L["boxes"][k][2], L["grow"], L["soft"]) if k in raw else ellipse_mask(L["boxes"][k])
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
    dst = os.path.join(out_dir, os.path.basename(src)[:-4] + "_EN.mp4")
    audio = os.path.join(ex, "en", f"{clip}_EN.wav")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", "24000/1001", "-i", "-", "-i", audio, "-map", "0:v", "-map", "1:a", *X264,
                            "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart", dst],
                           stdin=subprocess.PIPE)
    # shots kept exactly as already delivered (e.g. other speakers already done): taken from plan["base_from"]
    keep = [tuple(r) for r in plan.get("base_keep", [])]
    base_it = frames(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ex))), plan["base_from"])) \
        if keep else None
    for k, im in enumerate(frames(src)):
        if base_it is not None:
            bf = next(base_it)
            if any(a <= k <= b for a, b in keep):
                im = bf
        outf = im.astype(np.float32)
        for L in layers:
            if not (L["f0"] <= k <= L["f1"]):
                continue
            if L["it"] is None:
                L["it"] = frames(L["out"])
            syn = unzoom(im, next(L["it"]), L["zoom"], k)
            a = L["env"][k]
            if a <= 0 or k not in L["boxes"]:
                continue
            box = L["boxes"][k]
            near = [j for j in range(k - 12, k + 13) if j in L["pts"]]
            if near:
                j = min(near, key=lambda q: abs(q - k))
                bj = L["boxes"].get(j, box)
                shift = np.array([box[0] + box[2] / 2 - bj[0] - bj[2] / 2, box[1] + box[3] / 2 - bj[1] - bj[3] / 2])
                m = hull_mask(L["pts"][j] + shift, box[2], L["grow"], L["soft"]) * a
            else:
                m = ellipse_mask(box) * a
                L["fallback"] = L.get("fallback", 0) + 1
            outf = outf * (1 - m[..., None]) + syn.astype(np.float32) * m[..., None]
        enc.stdin.write(np.clip(outf + 0.5, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    for L in layers:
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
