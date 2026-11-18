# Melody EP101 — multi-language dubbing + lip-sync demo

Source: `Melody_EP101_H264_fragmento.mp4` (84 s, 1920x1080, 23.976 fps, stereo; dialogue, music and effects
mixed on one track; Spanish). Output: `Melody_EP101_multilanguage_demo.mp4` — same picture, length and frame
count (2013), with the dialogue switching language and the mouths lip-synced to each language.

## Language plan

| Clip time | Language | Lines | On screen |
|---|---|---|---|
| 0 – 16.5 s | Spanish (original audio) | 1–2 "¡Buf! ¿Pasó algo?" / "Lo de siempre…" | opening, station two-shot |
| 16.5 – 53.4 s | English | 3–7 "For how much longer?" … "Charlie is the picture of balance." | station two-shot (both girls) |
| 53.4 – 60.16 s | Hebrew | 8–10 "מוכנה." / "כמה שזה מעצבן אותי…" / "תבטיחי לי שיום אחד…" | Melody at the door, Layla close-up |
| 60.16 – 66.18 s | Portuguese (BR) | 11–13 "Não, esquece." / "Esse tal de futuro não existe." / "Meu presente é isso que vivemos aqui e agora, porque…" | Melody, radio studio |
| 66.18 s – end | French | 14 "Mon futur, c'est aujourd'hui." + the sung line "Mon avenir… c'est aujourd'hui" | Melody, then the close-up at the mic |

Each language switch sits in a pause of both neighbouring takes. The label (top left) shows the language
playing; the Phatty Acid logo is top right.

## Pipeline

1. **Separation** (`tools/separate.py`, Hybrid Demucs): dialogue stem and music/effects stem (= mix − dialogue,
   sample exact). A transcription pass on the music/effects stem finds no Spanish speech left in it.
2. **Analysis**: Whisper large-v3 (Spanish lines and word times), ECAPA speaker embeddings plus mouth movement
   per face (MediaPipe) → two speakers: **Melody** (blonde, lead) and **Layla** (dark curly hair). Every line's
   speaker was confirmed by both voice and mouth movement.
3. **Dubbing** (`tools/melody_dub.py`, Sync → ElevenLabs Dubbing v2, cloning strength 8): the dialogue stem of
   both dialogue scenes (36.4 s) dubbed into en-US, he, pt-BR and fr-FR, so each girl's voice is cloned from all
   of her lines and the acting/timing follows the original.
4. **Checks / fixes**: each dub transcribed back. Hebrew line 11 came out as "No, I don't promise anything"
   (masculine), so the Portuguese section starts at line 11. In the Portuguese dub, "Não" ran into Layla's line;
   line 11 is a separate take in Melody's cloned voice (`tools/melody_l11.py`, fitted with Praat PSOLA).
   A re-dub of lines 11–13 alone was tried and rejected ("Não tinha nada", "Por quê?").
5. **Voice match** (ECAPA, dub line vs the same actress's original lines): Melody 0.56–0.62, Layla 0.50–0.58 on
   lines long enough to measure, always closer to the right girl than to the other.
6. **French song** (`tools/melody_song_tts.py`, `tools/melody_song.py`): the dubbing engine spoke the lyrics
   instead of singing them. Instead: Melody's voice cloned (Sync/ElevenLabs IVC) from her clean Spanish lines,
   "Mon avenir… c'est aujourd'hui." voiced, and its 8 syllables placed on the 8 sung notes of "Mi futuro / …es
   hoy" with each note's original pitch contour (Praat PSOLA). Result: transcribes as "Mon avenir, c'est
   aujourd'hui.", pitch within 0.2 semitones (median) of her original melody. The "na-ra-na" part stays original.
7. **Lip sync** (`tools/melody_build.py` → `tools/build_lipsync_jobs.py` → `tools/full_stage.py`, sync-3):
   7 jobs, 42.4 s: English two-shot (one job per girl, each with only her own lines), Hebrew (Melody, Layla),
   Portuguese (2 shots), French line, French song close-up.
8. **Composite** (`tools/assemble_masked.py`): mouth-only masks, YUV compositing; the masked window covers both
   the dubbed speech and the original line (`also_windows`), so no original Spanish mouth movement shows
   without sound when a dub starts later than the original.
9. **Mix and render** (`tools/melody_render.py`): music/effects stem + voices; each dubbed section trimmed to
   the original voice's loudness (EBU R128). Overall −23.3 LUFS vs −23.4 LUFS original, every section within
   0.2 LU.

## QA

- 2013 frames, 1920x1080, 24000/1001, AAC 48 kHz 320k; same length as the original.
- Language ID of the final audio per section: es 0.97, en 0.94, he 0.98, pt 1.00, fr 0.97 (line), fr 0.97 (song).
- No frame-to-frame jumps beyond the original's outside the song close-up, where the large mouth changes are the lip sync itself
  (checked frame by frame: smooth, no flicker). Picture outside the mouths unchanged (encoding noise only).

## For a native speaker to spot-check

- Hebrew line 9 is heard as "כמה שזה מעצבן אותי שצריכה להתחבא" — colloquial (no "את"); fine for a demo,
  worth a native check before a client sees Hebrew as a selling point.

## Files

- `outputs/melody/Melody_EP101_multilanguage_demo.mp4` — master, x264 CRF 14 (138 MB; too big for GitHub, sent
  directly).
- `deliverables/melody/Melody_EP101_multilanguage_demo.mp4` — share copy, CRF 19 (81 MB), same audio.

## Cost (Sync)

Dubbing 4 × 36.4 s + song test 11 s + PT re-dub test 6.8 s (163 s, about $16 at $0.10/s); lip sync 42.4 s + 1.9 s
re-run of the PT shot (about $5.6 with sync-3); a few short TTS takes. About $22 in total. Three ElevenLabs
dubbing test runs also went through fal.ai while the Sync account was suspended; they are not used.
