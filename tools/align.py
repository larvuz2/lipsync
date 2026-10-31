"""Forced alignment of known text to speech (torchaudio MMS_FA, wav2vec2 CTC).

Whisper's word times are often off by 50-200 ms; for cutting single words in and out of a line we
align the known words to the audio instead.

    from align import align
    words = align(x, 48000, "Bring me my partridge")   # [(word, start_s, end_s), ...]
"""
import re
import unicodedata

import numpy as np

_M = {}


def _model():
    if not _M:
        import torch
        import torchaudio
        b = torchaudio.pipelines.MMS_FA
        _M.update(torch=torch, ta=torchaudio, model=b.get_model(with_star=False).eval(),
                  tok=b.get_tokenizer(), aligner=b.get_aligner(), sr=b.sample_rate)
    return _M


def words_of(text):
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.sub(r"[^a-z' ]", " ", t).split() if w.strip("'")]


def align(x, sr, text):
    m = _model()
    torch, ta = m["torch"], m["ta"]
    words = words_of(text)
    wav = torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32))[None]
    if sr != m["sr"]:
        wav = ta.functional.resample(wav, sr, m["sr"])
    with torch.inference_mode():
        em, _ = m["model"](wav)
    spans = m["aligner"](em[0], m["tok"](words))
    ratio = wav.shape[1] / em.shape[1] / m["sr"]
    return [(w, s[0].start * ratio, s[-1].end * ratio) for w, s in zip(words, spans)]


def find(words, target, start=0):
    """Index range [i, j) of the consecutive words that best match the target words."""
    import difflib
    tw = words_of(target)
    best = None
    for i in range(start, len(words) - len(tw) + 1):
        sc = sum(difflib.SequenceMatcher(None, words[i + k][0], tw[k]).ratio() for k in range(len(tw)))
        if best is None or sc > best[0]:
            best = (sc, i)
    return best[1], best[1] + len(tw), best[0] / len(tw)
