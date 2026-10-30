"""Turn stage-1 TTS takes into frame-accurate English dialogue tracks and lip-sync jobs.

    python3 tools/fit_and_build.py "media/LIP SYNC TEST" data/test1_lines.json exchange/test1

For every line:
  1. check each TTS take with Whisper (English) so mangled takes are dropped,
  2. keep the take whose natural length is closest to the Hungarian timing,
  3. time-stretch it (Rubber Band, pitch and formants preserved) to land exactly on the
     Hungarian phrase windows, and match the original phrase loudness.
The English track is the original dialogue track with only the Hungarian words swapped out, so
breaths, efforts and room tone stay. Test A (Sync auto-dub) is cut back into clips the same length.
Writes exchange/test1/build/*.wav, build/report.json and lipsync_jobs.json.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

SR = 48000
SPF = 2002  # samples per frame at 48 kHz and 24000/1001 fps


def load(path, ch=1):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", str(ch), "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, ch).T.copy()


def save(path, x, codec="pcm_s24le"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(x.shape[0]), "-i", "-",
                    "-c:a", codec, path], input=x.T.astype(np.float32).tobytes(), check=True)


def frame_db(x, hop=480):
    n = x.shape[-1] // hop
    return np.array([20 * np.log10(np.sqrt(np.mean(x[..., i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(n)])


def trim_silence(x, rel=40, pad=0.02):
    db = frame_db(x)
    on = np.where(db > db.max() - rel)[0]
    a = max(0, on[0] * 480 - int(pad * SR))
    b = min(x.shape[-1], (on[-1] + 1) * 480 + int(pad * SR))
    return x[..., a:b]


def split_phrases(x, rel=38, min_gap=0.15):
    db = frame_db(x)
    on = db > db.max() - rel
    segs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            segs.append([s, i]); s = None
    if s is not None:
        segs.append([s, len(on)])
    merged = []
    for g in segs:
        if merged and (g[0] - merged[-1][1]) * 480 / SR < min_gap:
            merged[-1][1] = g[1]
        else:
            merged.append(g)
    return [(a * 480, b * 480) for a, b in merged]


def stretch(x, target_len):
    """Rubber Band time-stretch to an exact sample count."""
    if x.shape[-1] == 0:
        return np.zeros((1, target_len), np.float32)
    tempo = x.shape[-1] / target_len
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        save(src, x, codec="pcm_f32le")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af",
                        f"rubberband=tempo={tempo:.6f}:window=short:formant=preserved:pitchq=quality:transients=mixed",
                        "-c:a", "pcm_f32le", dst], check=True)
        y = load(dst)
    y = y[:, :target_len]
    return np.pad(y, ((0, 0), (0, target_len - y.shape[1])))


def fade(x, ms=8):
    n = int(ms / 1000 * SR)
    x = x.copy()
    x[..., :n] *= np.linspace(0, 1, n)
    x[..., -n:] *= np.linspace(1, 0, n)
    return x


def rms(x):
    return float(np.sqrt(np.mean(x ** 2)) + 1e-12)


def norm_words(t):
    words = re.sub(r"[^a-z ]", " ", t.lower().replace("ó", "o")).split()
    # Any spelling of the name (Yahnko, Yanko, Janko, Yonko, Yanco...) counts as the name.
    return ["janko" if re.fullmatch(r"[jy][aeo]h?n[gk]?[ck]o", w) else w for w in words]


def wer(ref, hyp):
    r, h = norm_words(ref), norm_words(hyp)
    d = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        prev, d[0] = d.copy(), i
        for j in range(1, len(h) + 1):
            d[j] = min(prev[j] + 1, d[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(h)] / max(1, len(r))


def main():
    media, sheet_path, ex = sys.argv[1:4]
    sheet = json.load(open(sheet_path))
    s1 = json.load(open(os.path.join(ex, "stage1", "manifest.json")))
    build = os.path.join(ex, "build")
    os.makedirs(build, exist_ok=True)

    from faster_whisper import WhisperModel
    asr = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)

    takes = {}
    for t in s1["tts"]:
        x = trim_silence(load(os.path.join(ex, t["file"])))
        # Whisper expects 16 kHz samples.
        x16 = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(ex, t["file"]), "-ac", "1",
                                            "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout,
                            dtype=np.float32)
        segs, _ = asr.transcribe(x16, language="en", beam_size=5)
        heard = " ".join(s.text.strip() for s in segs)
        t.update({"x": x, "nat": x.shape[1] / SR, "heard": heard, "wer": wer(t["text"], heard)})
        takes.setdefault(t["line"], []).append(t)
        print(f"{t['name']}: {t['nat']:.2f}s wer={t['wer']:.2f} heard='{heard}'", flush=True)

    report, jobs = {}, []
    for clip, c in sheet["clips"].items():
        path = glob.glob(os.path.join(media, f"*{clip}.mp4"))[0]
        orig = load(path, ch=2)[0]  # channel 0 of the dual-mono original (ffmpeg's mono fold adds +3 dB)
        en = orig.copy()
        report[clip] = {"lines": []}
        for line in c["lines"]:
            wins = line["phrases"]
            target = sum(b - a for a, b in wins) if len(wins) > 1 else wins[0][1] - wins[0][0]
            span = wins[-1][1] - wins[0][0]
            cands = [t for t in takes.get(line["id"], []) if t["wer"] <= 0.25] or takes.get(line["id"], [])

            def cost(t):
                # Compare like with like: piecewise fits use speech-only time, otherwise the full span.
                ph = split_phrases(t["x"])
                if len(wins) > 1 and len(ph) == len(wins):
                    nat = sum(b - a for a, b in ph) / SR
                    return abs(np.log(target / nat))
                return abs(np.log(span / t["nat"]))

            best = min(cands, key=cost)
            ph = split_phrases(best["x"])
            pieces = list(zip(ph, wins)) if len(wins) > 1 and len(ph) == len(wins) else [((0, best["x"].shape[1]), (wins[0][0], wins[-1][1]))]
            ratios = []
            starts = sorted(w[0] for ln in c["lines"] for w in ln["phrases"])
            for (pa, pb), (wa, wb) in pieces:
                seg = best["x"][:, pa:pb]
                nat = seg.shape[1] / SR
                # Start where the actor starts. Length: as close to the Hungarian phrase as possible, but
                # never more than ±10 % off the natural English read (lip sync redraws the mouth to the
                # English anyway), and never running into the next phrase or past the clip end.
                nxt = min([s for s in starts if s > wa + 1e-6] + [len(orig) / SR + 0.12]) - 0.12
                dur = min(max(wb - wa, nat * 0.90), nat * 1.10, nxt - wa)
                a, b = int(round(wa * SR)), int(round((wa + dur) * SR))
                ratios.append((b - a) / seg.shape[1])
                y = stretch(seg, b - a)[0]
                ref = orig[a:b]
                y *= rms(ref) / rms(y)
                peak = np.abs(y).max()
                if peak > 0.89:
                    y *= 0.89 / peak
                y = fade(y)
                # Swap the Hungarian words for English: 30 ms crossfade margins.
                # Mute the whole span covered by either the Hungarian phrase or the English take.
                m = int(0.03 * SR)
                ma, mb = min(a, int(round(wa * SR))), max(b, int(round(wb * SR)))
                lo, hi = max(0, ma - m), min(len(en), mb + m)
                ramp = np.ones(hi - lo)
                ramp[: ma - lo] = np.linspace(1, 0, ma - lo)
                ramp[ma - lo: mb - lo] = 0
                ramp[mb - lo:] = np.linspace(0, 1, hi - mb)
                en[lo:hi] *= ramp
                en[a:b] += y
            info = {"id": line["id"], "hu": line["hu"], "en": line["variants"][best["variant"]]["en"],
                    "take": best["name"], "stability": best["stability"], "wer": round(best["wer"], 2),
                    "heard": best["heard"], "natural_s": round(best["nat"], 2),
                    "stretch": [round(r, 3) for r in ratios], "pieces": len(pieces)}
            report[clip]["lines"].append(info)
            print(clip, json.dumps(info, ensure_ascii=False), flush=True)
        save(os.path.join(build, f"{clip}_EN_B.wav"), np.stack([en, en]))

    # Test A: cut the auto-dub back into clips.
    ad = s1.get("autodub") or {}
    if ad.get("file"):
        off = json.load(open(os.path.join(ex, "inputs", "autodub_offsets.json")))
        dub = load(os.path.join(ex, ad["file"]))[0]
        total_in = max(o["start_sample"] + o["samples"] for o in off["offsets"].values()) + int(0.6 * SR)
        scale = len(dub) / total_in
        report["_autodub"] = {"in_s": round(total_in / SR, 3), "out_s": round(len(dub) / SR, 3), "scale": round(scale, 4)}
        for clip in sheet["clips"]:
            o = off["offsets"][clip]
            a = int(round(o["start_sample"] * scale))
            seg = dub[a:a + o["samples"]]
            seg = np.pad(seg, (0, o["samples"] - len(seg)))
            # Match the original dialogue level (active speech only) so A and B compare fairly.
            hu = load(glob.glob(os.path.join(media, f"*{clip}.mp4"))[0], ch=2)[0][:len(seg)]
            # Compare the loud speech frames (90th percentile of 10 ms loudness) of both tracks.
            seg = seg * 10 ** ((np.percentile(frame_db(hu), 90) - np.percentile(frame_db(seg), 90)) / 20)
            save(os.path.join(build, f"{clip}_EN_A.wav"), np.stack([seg, seg]))

    # Lip-sync jobs: only shots where the speaker is on camera.
    for clip, c in sheet["clips"].items():
        for sh in c["shots"]:
            if not sh["lipsync"]:
                continue
            f0, f1 = sh["first_frame"], sh["last_frame"]
            for ver, model in [("B", "sync-3"), ("A", "sync-3"), ("B", "lipsync-2-pro")]:
                src = os.path.join(build, f"{clip}_EN_{ver}.wav")
                if not os.path.exists(src):
                    continue
                x = load(src, ch=2)
                need = (f1 - f0 + 1) * SPF
                seg = x[:, f0 * SPF:]
                seg = np.pad(seg, ((0, 0), (0, max(0, need + SPF - seg.shape[1]))))[:, :need + SPF]
                rel = f"build/{clip}_f{f0}-{f1}_EN_{ver}.wav"
                save(os.path.join(ex, rel), seg)
                jobs.append({"name": f"{clip}_f{f0}-{f1}_{ver}_{model.replace('-', '')}", "clip": clip,
                             "first_frame": f0, "last_frame": f1, "audio": rel, "model": model, "face": sh.get("face")})
    json.dump(jobs, open(os.path.join(ex, "lipsync_jobs.json"), "w"), indent=1)
    json.dump(report, open(os.path.join(build, "report.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{len(jobs)} lip-sync jobs written")


if __name__ == "__main__":
    main()
