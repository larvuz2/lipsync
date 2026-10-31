"""Inventory + speaker analysis for every clip in a folder (free, local).

    python3 tools/analyze_clips.py <clips_dir> <out_dir> [yunet.onnx]

Per clip (sorted by split number, which is the episode order):
  - frames / fps / size / audio length
  - shot cuts (ffmpeg scene score)
  - speech phrases from the dialogue track (loudness)
  - faces on every frame (OpenCV YuNet), tracked within each shot
  - for every phrase, which face's mouth moves with the speech (correlation of mouth-region
    motion with the audio envelope). Low scores everywhere = speaker is off camera.
Writes <out_dir>/analysis.json and a contact sheet per clip with face boxes and track ids.
"""
import glob
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
except Exception:  # pragma: no cover
    mp = None

_LM = None


def landmarker(model_path):
    global _LM
    if _LM is None and mp is not None and model_path and os.path.exists(model_path):
        opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=model_path),
                                            running_mode=vision.RunningMode.IMAGE, num_faces=1,
                                            output_face_blendshapes=True, min_face_detection_confidence=0.3)
        _LM = vision.FaceLandmarker.create_from_options(opts)
    return _LM


def mouth_open(frame_bgr, box_half, lm):
    """jawOpen blendshape + inner-lip aperture for one face (box in 960x540 coords), via an upscaled crop."""
    x, y, w, h = [v * 2 for v in box_half]
    side = max(w, h) * 1.8
    cx, cy = x + w / 2, y + h / 2
    H, W = frame_bgr.shape[:2]
    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x1, y1 = int(min(W, cx + side / 2)), int(min(H, cy + side / 2))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    crop = cv2.resize(frame_bgr[y0:y1, x0:x1], (256, 256), interpolation=cv2.INTER_CUBIC)
    res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
    if not res.face_landmarks:
        return None
    pts = res.face_landmarks[0]
    jaw = [b.score for b in res.face_blendshapes[0] if b.category_name == "jawOpen"][0]
    ap = abs(pts[13].y - pts[14].y) / (abs(pts[61].x - pts[291].x) + 1e-6)
    return float(jaw), float(ap)

SR = 48000


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                          "stream=nb_read_frames,r_frame_rate,width,height", "-of", "json", path],
                         capture_output=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = map(int, s["r_frame_rate"].split("/"))
    return int(s["nb_read_frames"]), num / den, s["r_frame_rate"], s["width"], s["height"]


def audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2)[:, 0].copy()


def cuts(path, fps):
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "scale=320:-2,select='gt(scene,0.14)',metadata=print:file=-",
                          "-an", "-f", "null", "-"], capture_output=True, text=True).stdout
    ts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", out)]
    return sorted({int(round(t * fps)) for t in ts if t * fps >= 2})


def phrases(x, floor_db=-52.0, rel_db=32.0, min_gap=0.18, min_len=0.08):
    hop = SR // 100
    n = len(x) // hop
    db = np.array([20 * np.log10(np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(n)])
    db = np.convolve(db, np.ones(3) / 3, mode="same")
    thr = max(floor_db, db.max() - rel_db)
    on = db > thr
    segs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            segs.append([s, i]); s = None
    if s is not None:
        segs.append([s, n])
    merged = []
    for g in segs:
        if merged and (g[0] - merged[-1][1]) / 100 < min_gap:
            merged[-1][1] = g[1]
        else:
            merged.append(g)
    return [(a / 100, b / 100) for a, b in merged if (b - a) / 100 >= min_len]


def detect_faces(path, model, nframes):
    det = cv2.FaceDetectorYN.create(model, "", (960, 540), 0.6, 0.3, 50)
    cap = cv2.VideoCapture(path)
    per_frame, grays = [], []
    for _ in range(nframes):
        ok, fr = cap.read()
        if not ok:
            break
        small = cv2.resize(fr, (960, 540))
        _, faces = det.detect(small)
        per_frame.append([] if faces is None else [f.copy() for f in faces])
        grays.append(fr)
    return per_frame, grays


def track(per_frame, shots):
    """Greedy IoU tracking inside each shot. Returns list of tracks: {shot, frames:{i: face}}."""
    tracks = []
    for s0, s1 in shots:
        live = []
        for i in range(s0, min(s1 + 1, len(per_frame))):
            used = set()
            for f in per_frame[i]:
                box = f[:4]
                best, bi = 0.25, None
                for k, t in enumerate(live):
                    if k in used:
                        continue
                    last_i = max(t["frames"])
                    if i - last_i > 8:
                        continue
                    pb = t["frames"][last_i][:4]
                    ix = max(0, min(box[0] + box[2], pb[0] + pb[2]) - max(box[0], pb[0]))
                    iy = max(0, min(box[1] + box[3], pb[1] + pb[3]) - max(box[1], pb[1]))
                    inter = ix * iy
                    iou = inter / (box[2] * box[3] + pb[2] * pb[3] - inter + 1e-6)
                    if iou > best:
                        best, bi = iou, k
                if bi is None:
                    live.append({"shot": [s0, s1], "frames": {i: f}})
                    used.add(len(live) - 1)
                else:
                    live[bi]["frames"][i] = f
                    used.add(bi)
        tracks += [t for t in live if len(t["frames"]) >= 3]
    return tracks


def mouth_motion(grays, t):
    vals = {}
    prev = None
    for i in sorted(t["frames"]):
        f = t["frames"][i]
        x, y, w, h = f[:4]
        rmx, rmy, lmx, lmy = f[10], f[11], f[12], f[13]
        cx, cy = (rmx + lmx) / 2, (rmy + lmy) / 2
        mw = max(abs(lmx - rmx) * 1.6, w * 0.35)
        mh = h * 0.32
        x0, x1 = int(max(0, cx - mw / 2)), int(min(959, cx + mw / 2))
        y0, y1 = int(max(0, cy - mh * 0.45)), int(min(539, cy + mh * 0.55))
        if x1 - x0 < 4 or y1 - y0 < 4:
            prev = None
            continue
        crop = cv2.resize(grays[i][y0:y1, x0:x1], (32, 24)).astype(np.float32)
        crop = (crop - crop.mean()) / (crop.std() + 1e-6)
        if prev is not None and prev[0] == i - 1:
            vals[i] = float(np.abs(crop - prev[1]).mean())
        prev = (i, crop)
    return vals


def main():
    src, out = sys.argv[1], sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else "yunet.onnx"
    os.makedirs(out, exist_ok=True)
    clips = sorted(glob.glob(os.path.join(src, "*.mp4")), key=lambda p: int(re.search(r"Splits(\d+)", p).group(1)))
    results = []
    for path in clips:
        cid = re.search(r"Splits(\d+)", path).group(1)
        n, fps, rate, W, H = probe(path)
        x = audio(path)
        cs = cuts(path, fps)
        bounds = [0] + cs + [n]
        shots = [[bounds[k], bounds[k + 1] - 1] for k in range(len(bounds) - 1)]
        ph = phrases(x)
        per_frame, grays = detect_faces(path, model, n)
        tracks = track(per_frame, shots)
        spf = SR / fps
        env = np.array([np.sqrt(np.mean(x[int(i * spf):int((i + 1) * spf)] ** 2)) if int((i + 1) * spf) <= len(x) else 0
                        for i in range(n)])
        envd = np.r_[0, np.abs(np.diff(env))]
        trk_out = []
        lmk = landmarker(model.replace("yunet.onnx", "face_landmarker.task"))
        for k, t in enumerate(tracks):
            mm = {}
            for i, f in t["frames"].items():
                r = mouth_open(grays[i], f[:4], lmk) if lmk else None
                if r is not None:
                    mm[i] = r[1]  # inner-lip aperture
            fr = sorted(t["frames"])
            mid = fr[len(fr) // 2]
            f = t["frames"][mid]
            trk_out.append({"id": k, "shot": t["shot"], "first": fr[0], "last": fr[-1], "n": len(fr),
                            "ref_frame": int(mid), "center": [int((f[0] + f[2] / 2) * 2), int((f[1] + f[3] / 2) * 2)],
                            "size": int(f[3] * 2), "score": round(float(f[-1]), 2), "_mm": mm})
        ph_out = []
        for a, b in ph:
            fa, fb = int(a * fps), min(n - 1, int(b * fps))
            cands = []
            for t in trk_out:
                idx = [i for i in range(fa, fb + 1) if i in t["_mm"]]
                if len(idx) < max(4, 0.4 * (fb - fa + 1)):
                    continue
                m = np.array([t["_mm"][i] for i in idx])
                e = np.array([env[i] for i in idx])
                corr = float(np.corrcoef(m, e)[0, 1]) if m.std() > 0 and e.std() > 0 else 0.0
                # mouth activity during speech vs the same face outside speech
                outside = [v for i, v in t["_mm"].items() if not (fa - 3 <= i <= fb + 3)]
                ratio = float(m.std() / (np.std(outside) + 1e-3)) if len(outside) > 3 else None
                cands.append({"track": t["id"], "coverage": round(len(idx) / (fb - fa + 1), 2), "corr": round(corr, 2),
                              "open_mean": round(float(m.mean()), 3), "open_std": round(float(m.std()), 3),
                              "std_ratio": None if ratio is None else round(ratio, 2)})
            ph_out.append({"start": round(a, 2), "end": round(b, 2), "frames": [fa, fb], "faces": cands})
        for t in trk_out:
            t.pop("_mm")
        frame_tracks = {}
        for k, t in enumerate(tracks):
            for i, f in t["frames"].items():
                frame_tracks.setdefault(i, []).append((k, [float(v) for v in f[:4]]))
        rec = {"clip": cid, "file": os.path.basename(path), "frames": n, "fps": rate, "size": [W, H],
               "audio_s": round(len(x) / SR, 3), "cuts": cs, "shots": shots, "phrases": ph_out, "tracks": trk_out,
               "speech_s": round(sum(b - a for a, b in ph), 2)}
        results.append(rec)
        sheet(path, rec, frame_tracks, os.path.join(out, f"sheet_{cid}.jpg"))
        print(f"{cid}: {n}f {rec['audio_s']}s shots={len(shots)} phrases={len(ph)} speech={rec['speech_s']}s tracks={len(trk_out)}",
              flush=True)
    json.dump(results, open(os.path.join(out, "analysis.json"), "w"), indent=1)


def sheet(path, rec, frame_tracks, dst):
    """6 frames spread over the clip with tracked face boxes (T<id>) and speech marked."""
    cap = cv2.VideoCapture(path)
    n = rec["frames"]
    picks = sorted(set([int(n * k / 6 + n / 12) for k in range(6)]))
    tiles = []
    for i in picks:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = cap.read()
        if not ok:
            continue
        fr = cv2.resize(fr, (640, 360))
        t_s = i * rec["audio_s"] / n
        speaking = any(p["start"] <= t_s <= p["end"] for p in rec["phrases"])
        for k, (x, y, w, h) in frame_tracks.get(i, []):
            x, y, w, h = [int(v * 640 / 960) for v in (x, y, w, h)]
            cv2.rectangle(fr, (x, y), (x + w, y + h), (0, 255, 255), 2)
            cv2.putText(fr, f"T{k}", (x, max(14, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        label = f"{rec['clip']} f{i} t={t_s:.2f}{' SPEECH' if speaking else ''}"
        cv2.rectangle(fr, (0, 0), (330, 22), (0, 0, 0), -1)
        cv2.putText(fr, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255) if speaking else (255, 255, 255), 1)
        tiles.append(fr)
    while len(tiles) < 6:
        tiles.append(np.zeros((360, 640, 3), np.uint8))
    grid = np.vstack([np.hstack(tiles[0:3]), np.hstack(tiles[3:6])])
    cv2.imwrite(dst, grid, [cv2.IMWRITE_JPEG_QUALITY, 80])


if __name__ == "__main__":
    main()
