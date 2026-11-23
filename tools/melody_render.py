"""Melody EP101 demo: final render = lip-synced picture + demo mix + corner labels.

    python3 tools/melody_render.py <composite.mp4> work/melody <out.mp4> [crf] [timeline] [mix.wav]

timeline: "es:0,en:16.5,he:53.4" (language label from that clip second on); default: the four-language demo.

Top left: the language now playing (crossfades at each switch). Top right: the Phatty Acid logo.
Audio: work/melody/mix/final_mix.wav (AAC 320k). Video: x264 (CRF 14 master, or the given CRF), 1920x1080,
24000/1001, frame count checked.
"""
import os
import subprocess
import sys

# language label timeline (clip seconds); each switch sits in the pause before that language's first line
TIMELINE = [("es", 0.0), ("en", 16.50), ("he", 53.40), ("pt", 60.16), ("fr", 66.18)]
FADE = 0.25
MARGIN_X, MARGIN_Y = 40, 36


def main():
    comp, w, out = sys.argv[1], sys.argv[2], sys.argv[3]
    crf = sys.argv[4] if len(sys.argv) > 4 else "14"
    timeline = [(c, float(t)) for c, t in (p.split(":") for p in sys.argv[5].split(","))] \
        if len(sys.argv) > 5 else TIMELINE
    mix = sys.argv[6] if len(sys.argv) > 6 else os.path.join(w, "mix", "final_mix.wav")
    lab = os.path.join(w, "labels")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", comp],
                               capture_output=True, text=True).stdout)
    inputs = ["-i", comp, "-i", mix]
    filt, last = [], "[0:v]"
    for k, (code, t0) in enumerate(timeline):
        t1 = timeline[k + 1][1] if k + 1 < len(timeline) else dur + 1
        inputs += ["-loop", "1", "-framerate", "24000/1001", "-i", os.path.join(lab, f"lang_{code}.png")]
        idx = 2 + k
        a = max(0.0, t0 - FADE / 2)
        fades = []
        if k > 0:
            fades.append(f"fade=t=in:st={a:.3f}:d={FADE}:alpha=1")
        if k + 1 < len(timeline):
            fades.append(f"fade=t=out:st={t1 - FADE / 2:.3f}:d={FADE}:alpha=1")
        chain = ",".join(["format=rgba"] + fades)
        filt.append(f"[{idx}:v]{chain}[l{k}]")
        filt.append(f"{last}[l{k}]overlay=x={MARGIN_X}:y={MARGIN_Y}:shortest=1:"
                    f"enable='between(t,{a:.3f},{t1 + FADE:.3f})'[v{k}]")
        last = f"[v{k}]"
    bidx = 2 + len(timeline)
    inputs += ["-loop", "1", "-framerate", "24000/1001", "-i", os.path.join(lab, "brand.png")]
    filt.append(f"{last}[{bidx}:v]overlay=x=W-w-{MARGIN_X}:y={MARGIN_Y}:shortest=1,format=yuv420p[vout]")
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[vout]", "-map", "1:a",
           "-c:v", "libx264", "-crf", crf, "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "24000/1001",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
           "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-t", f"{dur:.6f}", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", out], capture_output=True, text=True).stdout.strip()
    print(out, "frames", n)


if __name__ == "__main__":
    main()
