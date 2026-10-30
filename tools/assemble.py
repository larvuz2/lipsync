"""Build the final English clips (same file names as the source) and review reels.

    python3 tools/assemble.py "media/LIP SYNC TEST" data/test1_lines.json exchange/test1 outputs/test1

For each version:
  B_sync3        our translation + cloned voice + sync-3            -> outputs/.../EN/   (main deliverable)
  A_sync3        Sync/ElevenLabs auto-dub audio + sync-3            -> outputs/.../alt_A_autodub/
  B_lipsync2pro  our audio + lipsync-2-pro (cheaper model check)    -> outputs/.../alt_C_lipsync2pro/
Shots without an on-camera speaker keep the original frames. Every output is checked to have
exactly the source's frame count.
"""
import glob
import json
import os
import subprocess
import sys

VERSIONS = [("B", "sync3", "EN"), ("A", "sync3", "alt_A_autodub"), ("B", "lipsync2pro", "alt_C_lipsync2pro")]
FPS = "24000/1001"
X264 = ["-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-r", FPS]


def run(cmd):
    subprocess.run(cmd, check=True)


def nframes(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return int(out.strip())


def build_clip(src, clip, c, ex, ver, model, out_dir):
    name = os.path.basename(src)
    dst = os.path.join(out_dir, name)
    os.makedirs(out_dir, exist_ok=True)
    audio = os.path.join(ex, "build", f"{clip}_EN_{ver}.wav")
    if not os.path.exists(audio):
        return None
    inputs, chains, labels = ["-i", src], [], []
    for k, sh in enumerate(c["shots"]):
        f0, f1 = sh["first_frame"], sh["last_frame"]
        n = f1 - f0 + 1
        gen = os.path.join(ex, "stage2", "out", f"{clip}_f{f0}-{f1}_{ver}_{model}.mp4")
        if sh["lipsync"] and not os.path.exists(gen):
            return None  # this version wasn't generated
        if sh["lipsync"]:
            inputs += ["-i", gen]
            idx, start = len(inputs) // 2 - 1, 0
        else:
            idx, start = 0, f0
        chains.append(f"[{idx}:v]trim=start_frame={start}:end_frame={start + n},setpts=PTS-STARTPTS,"
                      f"scale=1920:1080:flags=lanczos,format=yuv420p,settb=AVTB,fps={FPS}[s{k}]")
        labels.append(f"[s{k}]")
    lipsynced = any(sh["lipsync"] for sh in c["shots"])
    if lipsynced:
        fc = ";".join(chains) + f";{''.join(labels)}concat=n={len(labels)}:v=1:a=0[v]"
        run(["ffmpeg", "-v", "error", "-y", *inputs, "-i", audio, "-filter_complex", fc, "-map", "[v]",
             "-map", f"{len(inputs) // 2}:a", *X264, "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
             "-shortest", "-movflags", "+faststart", dst])
    else:  # no on-camera speaker: picture untouched, audio replaced
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", dst])
    run(["ffmpeg", "-v", "error", "-y", "-i", audio, "-c:a", "libmp3lame", "-b:a", "320k",
         os.path.splitext(dst)[0] + ".mp3"])
    got, want = nframes(dst), c["frames"]
    status = "OK" if got == want else f"FRAME MISMATCH {got} vs {want}"
    print(f"{out_dir.split('/')[-1]}/{clip}: {status}")
    return dst


def label(path, text, out):
    run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf",
         f"scale=1280:-2,drawtext=text='{text}':x=24:y=24:fontsize=30:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=10",
         "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-r", FPS, "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-ac", "2", out])


def main():
    media, sheet_path, ex, out = sys.argv[1:5]
    sheet = json.load(open(sheet_path))
    reels = []
    for clip, c in sheet["clips"].items():
        src = glob.glob(os.path.join(media, f"*{clip}.mp4"))[0]
        parts = []
        tmp = os.path.join(out, "_tmp")
        os.makedirs(tmp, exist_ok=True)
        label(src, f"{clip}  HU original", os.path.join(tmp, f"{clip}_0.mp4"))
        parts.append(os.path.join(tmp, f"{clip}_0.mp4"))
        for i, (ver, model, folder) in enumerate(VERSIONS, 1):
            dst = build_clip(src, clip, c, ex, ver, model, os.path.join(out, folder))
            if dst:
                tag = {"EN": "EN  ours + sync-3", "alt_A_autodub": "EN  Sync auto-dub + sync-3",
                       "alt_C_lipsync2pro": "EN  ours + lipsync-2-pro"}[folder]
                p = os.path.join(tmp, f"{clip}_{i}.mp4")
                label(dst, f"{clip}  {tag}", p)
                parts.append(p)
        lst = os.path.join(tmp, f"{clip}.txt")
        open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
        reel = os.path.join(out, "review", f"{clip}_compare.mp4")
        os.makedirs(os.path.dirname(reel), exist_ok=True)
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", reel])
        reels.append(reel)
    # Whole scene in English, back to back (main version).
    en = [glob.glob(os.path.join(out, "EN", f"*{clip}.mp4")) for clip in sheet["clips"]]
    en = [e[0] for e in en if e]
    if en:
        tmp = os.path.join(out, "_tmp")
        parts = []
        for k, p in enumerate(en):
            q = os.path.join(tmp, f"scene_{k}.mp4")
            label(p, "EN", q)
            parts.append(q)
        lst = os.path.join(tmp, "scene.txt")
        open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
             os.path.join(out, "review", "scene_EN.mp4")])
    print("reels:", reels)


if __name__ == "__main__":
    main()
