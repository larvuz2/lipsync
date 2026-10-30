"""Split each clip's audio into dialogue ("vocals") and music+effects ("background").

Uses Hybrid Demucs weights published by PyTorch (torchaudio HDEMUCS_HIGH_MUSDB_PLUS).

    pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
    python3 tools/separate.py "media/LIP SYNC TEST" work/stems 87434 87646 87725 ...

Writes <out>/<clip>_vocals.wav and <out>/<clip>_bg.wav (48 kHz stereo float WAV, same length as
the clip's audio track).
"""
import glob
import os
import subprocess
import sys

import numpy as np
import torch
import torchaudio
from torchaudio.pipelines import HDEMUCS_HIGH_MUSDB_PLUS

SR_IN = 48000


def load(path: str) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR_IN),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()


def save(path: str, x: np.ndarray, sr: int) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", str(x.shape[0]),
                    "-i", "-", "-c:a", "pcm_f32le", path], input=x.T.astype(np.float32).tobytes(), check=True)


def main() -> None:
    src, out, clips = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(out, exist_ok=True)
    bundle = HDEMUCS_HIGH_MUSDB_PLUS
    model = bundle.get_model().eval()
    sr = bundle.sample_rate  # 44100
    names = model.sources  # ['drums', 'bass', 'other', 'vocals']
    torch.set_num_threads(os.cpu_count() or 4)
    for clip in clips:
        path = glob.glob(os.path.join(src, f"*{clip}.mp4"))[0]
        x = load(path)
        n_in = x.shape[1]
        wav = torchaudio.functional.resample(torch.from_numpy(x), SR_IN, sr)
        ref = wav.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8
        # Pad 1 s each side so edges separate cleanly.
        pad = sr
        inp = torch.nn.functional.pad((wav - mean) / std, (pad, pad), mode="reflect")[None]
        with torch.inference_mode():
            est = model(inp)[0][..., pad:-pad] * std + mean
        stems = {n: torchaudio.functional.resample(est[i], sr, SR_IN).numpy() for i, n in enumerate(names)}
        vocals = stems["vocals"][:, :n_in]
        vocals = np.pad(vocals, ((0, 0), (0, n_in - vocals.shape[1])))
        bg = x - vocals  # residual keeps everything that isn't dialogue, sample-exact
        save(os.path.join(out, f"{clip}_vocals.wav"), vocals, SR_IN)
        save(os.path.join(out, f"{clip}_bg.wav"), bg, SR_IN)
        db = lambda v: 20 * np.log10(np.sqrt(np.mean(v ** 2)) + 1e-12)
        print(f"{clip}: mix {db(x):.1f} dB | vocals {db(vocals):.1f} dB | background {db(bg):.1f} dB", flush=True)


if __name__ == "__main__":
    main()
