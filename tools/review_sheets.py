"""Per-clip review sheets for deciding who speaks on camera.

    python3 tools/review_sheets.py exchange/full/analysis/analysis.json media/full exchange/full/review [yunet.onnx]

For every shot that contains speech: 4 frames during the speech with numbered face boxes (by track id
from analysis.json, matched by position), and a mouth filmstrip (8 frames) for each face so lip
movement can be judged. One JPG per clip.
"""
import glob
import json
import os
import sys

import cv2
import numpy as np


def main():
    an, media, out = sys.argv[1:4]
    model = sys.argv[4] if len(sys.argv) > 4 else "yunet.onnx"
    os.makedirs(out, exist_ok=True)
    det = cv2.FaceDetectorYN.create(model, "", (960, 540), 0.6, 0.3, 50)
    for rec in json.load(open(an)):
        path = glob.glob(os.path.join(media, f"*Splits{rec['clip']}.mp4"))[0]
        cap = cv2.VideoCapture(path)
        fps = rec["frames"] / rec["audio_s"] if rec["audio_s"] else 23.976
        fps = 24000 / 1001
        frames = []
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            frames.append(fr)
        blocks = []
        for si, (s0, s1) in enumerate(rec["shots"]):
            sp = [(max(s0, int(p["start"] * fps)), min(s1, int(p["end"] * fps))) for p in rec["phrases"]]
            sp = [(a, b) for a, b in sp if b - a >= 2]
            if not sp:
                continue
            speech_frames = [i for a, b in sp for i in range(a, b + 1)]
            picks = [speech_frames[int(k * (len(speech_frames) - 1) / 3)] for k in range(4)]
            strip_idx = [speech_frames[int(k * (len(speech_frames) - 1) / 7)] for k in range(8)]
            thumbs = []
            faces_ref = None
            for i in picks:
                fr = frames[i].copy()
                small = cv2.resize(fr, (960, 540))
                _, faces = det.detect(small)
                faces = [] if faces is None else sorted([f for f in faces], key=lambda f: f[0])
                if faces_ref is None and len(faces):
                    faces_ref = (i, faces)
                th = cv2.resize(fr, (480, 270))
                for k, f in enumerate(faces):
                    x, y, w, h = [int(v / 2) for v in f[:4]]
                    cv2.rectangle(th, (x, y), (x + w, y + h), (0, 255, 255), 2)
                    cx, cy = int((f[0] + f[2] / 2) * 2), int((f[1] + f[3] / 2) * 2)
                    cv2.putText(th, f"F{k} ({cx},{cy})", (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
                t = i / fps
                cv2.rectangle(th, (0, 0), (300, 18), (0, 0, 0), -1)
                cv2.putText(th, f"{rec['clip'][3:]} shot{si} f{i} t={t:.2f}", (3, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                thumbs.append(th)
            row = np.hstack(thumbs)
            rows = [row]
            # Mouth filmstrips: follow each face found on the middle pick by nearest box over the strip frames.
            mid = picks[1]
            _, mf = det.detect(cv2.resize(frames[mid], (960, 540)))
            mf = [] if mf is None else sorted([f for f in mf], key=lambda f: f[0])
            for k, f0 in enumerate(mf[:4]):
                cells = []
                prev = f0
                for i in strip_idx:
                    _, ff = det.detect(cv2.resize(frames[i], (960, 540)))
                    if ff is not None and len(ff):
                        d = [np.hypot((g[0] + g[2] / 2) - (prev[0] + prev[2] / 2), (g[1] + g[3] / 2) - (prev[1] + prev[3] / 2)) for g in ff]
                        g = ff[int(np.argmin(d))]
                        if min(d) < max(prev[2], prev[3]) * 1.2:
                            prev = g
                    x, y, w, h = [v * 2 for v in prev[:4]]
                    cx, cy = x + w / 2, y + h * 0.72
                    side = max(w, h) * 0.75
                    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
                    x1, y1 = int(min(1920, cx + side / 2)), int(min(1080, cy + side / 2))
                    crop = frames[i][y0:y1, x0:x1]
                    crop = cv2.resize(crop, (240, 240)) if crop.size else np.zeros((240, 240, 3), np.uint8)
                    cv2.putText(crop, f"F{k} f{i}", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                    cells.append(crop)
                rows.append(np.hstack(cells))
            wmax = max(r.shape[1] for r in rows)
            rows = [np.pad(r, ((0, 0), (0, wmax - r.shape[1]), (0, 0))) for r in rows]
            blocks.append(np.vstack(rows + [np.full((6, wmax, 3), 80, np.uint8)]))
        if not blocks:
            continue
        wmax = max(b.shape[1] for b in blocks)
        img = np.vstack([np.pad(b, ((0, 0), (0, wmax - b.shape[1]), (0, 0))) for b in blocks])
        cv2.imwrite(os.path.join(out, f"review_{rec['clip']}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 72])
        print(rec["clip"], img.shape, flush=True)


if __name__ == "__main__":
    main()
