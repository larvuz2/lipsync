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
| 66.18 s – end | French | 14 "Mon futur, c'est aujourd'hui." + the ending "Mon futur ? Mon futur, c'est aujourd'hui." (her humming before it stays original) | Melody, then the close-up at the mic |

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
6. **Ending** (`tools/melody_dub_end.py`): she hums, then says "¿Mi futuro? Mi futuro es hoy" softly. The humming
   stays original (identical audio). The spoken line is dubbed like the others (Sync, fr-FR), with Melody's lines
   12–14 in the same dub source so the voice and wording match line 14: "Mon futur ? Mon futur, c'est
   aujourd'hui." In the original she says it barely above the music; the French sits about 4 dB above her original
   level (−28 LUFS) so it is clearly understood. (Client review: a first version re-sung the line on her melody;
   it was replaced — it is speech, not singing.)
7. **Lip sync** (`tools/melody_build.py` → `tools/build_lipsync_jobs.py` → `tools/full_stage.py`, sync-3):
   7 jobs, 42.4 s: English two-shot (one job per girl, each with only her own lines), Hebrew (Melody, Layla),
   Portuguese (2 shots), French line, French ending close-up.
8. **Composite** (`tools/assemble_masked.py`): mouth-only masks, YUV compositing; the masked window covers both
   the dubbed speech and the original line (`also_windows`), so no original Spanish mouth movement shows
   without sound when a dub starts later than the original.
   Ending close-up (client review: "glitches and flickers"): her face is very close, moving and under changing blue
   light, so the face detector's box jumped in size and place from frame to frame. On 4 frames (82.50–82.54 s,
   82.83–82.87 s) the mask was shifted by those jumps off her mouth and the original Spanish mouth showed for two
   frames at a time. The job is now marked `steady`: the box is a temporal median, the mouth outline is searched
   where the mouth was on the last frame (found on 88/88 frames), and the mask's grow/feather use the shot's median
   face size. All 59 frames of the line now carry the lip-synced mouth (was 55); the other shots are unchanged.
9. **Mix and render** (`tools/melody_render.py`): music/effects stem + voices; each dubbed section trimmed to
   the original voice's loudness (EBU R128). Overall −23.3 LUFS vs −23.4 LUFS original, every section within
   0.2 LU.

## QA

- 2013 frames, 1920x1080, 24000/1001, AAC 48 kHz 320k; same length as the original.
- Language ID of the final audio per section: es 0.97, en 0.90, he 0.98, pt 0.99, fr 0.97 (line 14), fr 0.98 (ending).
- Humming before the ending: correlation with the original 1.0000 (untouched).
- No frame-to-frame jumps beyond the original's outside the close-up at the mic, where the large mouth changes are the lip
  sync itself (checked frame by frame: smooth, no flicker). Picture outside the mouths unchanged (encoding noise only).

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

---

# Version 2 — Spanish → English → Hebrew (native accents)

Client: only English and Hebrew ("Israel is a big market"), and English "without accents, like native English
speakers". Output: `Melody_EP101_ES_EN_HE_demo.mp4`.

| Clip time | Language | Lines (approved script) |
|---|---|---|
| 0 – 16.5 s | Spanish (original audio) | 1 Layla "¡Buf! ¡Ey! ¿Pasó algo?" · 2 Melody "Lo de siempre…" |
| 16.5 – 53.4 s | English | 3 Layla "How much longer?" · 4 Melody "I know, don't even say it." · 5 Melody "What about Charlie? Everything okay?" · 6 Layla "With him, everything is always more than fine." · 7 Layla "Charlie is the picture of balance." |
| 53.4 s – end | Hebrew | 8 Melody "מוכנה." · 9 Layla "כמה זה מעצבן אותי שאת צריכה להסתתר!" · 10 Layla "תבטיחי לי שיום אחד…" · 11 Melody "אל תגידי לי כלום." · 12 "זה העתיד, והעתיד לא קיים." · 13 "ההווה שלי זה מה שאני חיה כאן ועכשיו, כי…" · 14 "העתיד שלי הוא היום." · (humming: original) · 15 "העתיד שלי? העתיד שלי הוא היום." |

## Why line-by-line voicing instead of the auto-dub

Tried first (`tools/melody_dub_pieces.py`): Sync dubbing with lower cloning strength (2 and 4 for English, 4 and 6
for Hebrew). Lower strength gives a native accent but loses the voices (Layla's voice match fell to ~0 at strength
2), the English wording drifted from the script, and several Hebrew lines came out wrong at both strengths (line 11
nonsense, line 14 "ancient" instead of "future"). Not used.

Used (`tools/melody_tts_lines.py`, `tools/melody_build_enhe.py`): each girl's voice cloned (Sync/ElevenLabs) from
her own clean Spanish lines; every line voiced from the approved script, 3–6 takes per line; per line the take with
the most native accent (English, CommonAccent classifier) and the closest voice was picked. Every Hebrew take
transcribes exactly as the script. Line 6: with "everything's" every take read British; "everything is" reads
American (same words). Each take: long pauses shortened to 0.18 s, fitted to its slot with Praat PSOLA (0.85–1.0x),
pitch moved partly toward the actress's pitch in that same line (at most 2.5 semitones), level matched to the original
line (EBU R128; the ending +4.3 dB as in v1). English accent after fitting: US on lines 3, 4, 6, 7; line 5 North
American (classified Canada).

Lip sync: same 7 shots, sync-3, re-run on the new audio; mouth-only masks covering the new line and the original
line; the close-up at the mic uses the `steady` mask.

## Client review: "the English section is awful lip sync" — cause and fix

Same lip-sync process as Rise of the Raven (sync-3 + mouth-only masked composite). What differed:

- **Timing.** sync-3 keeps much of the actor's original mouth rhythm (it preserves the performance; its output
  mouth followed Melody's original Spanish mouth at r = 0.82). On Raven the English always followed the original
  timing (auto-dub, or the King's phrases re-timed onto his mouth). In version 2 the native-accent lines were placed
  by Whisper's word times, which ran up to 0.5 s early (e.g. Melody's line 4 really starts at 19.03 s, not 18.68 s),
  and some English lines were ~50 % longer than the Spanish — so the mouths moved against the English
  (mouth vs. speech r = −0.24 for Melody).
- **Fix:** every line (English and Hebrew) now starts where the actress really starts (from the dialogue stem's
  energy), is fitted toward her original length (0.75–1.12x, Praat PSOLA), and phrase by phrase where both have
  phrases (line 5). Two English lines use slightly shorter wordings so they fit her mouth: "I know, don't say it."
  and "With him, it's always more than fine." (US accent 0.99 on both). Layla's Hebrew line 10 is cut off after
  "תבטיחי לי ש-" by Melody's line 11, as in the original, so line 11 starts on Melody's own mouth. New speech vs. the
  original mouth rhythm: r = +0.26 for both girls (was −0.09 / −0.03; the Spanish itself scores ~0.3).
- **English two-shot faces** (~200 px, 3/4 view) are sent as tracked, enlarged crops (as for small faces in Raven),
  with Sync's own speaker detection in the crop.
- Tested and not used: sync-3 with higher temperature (ignored by sync-3); lipsync-2-pro (moves the mouth more but
  misplaces and smears it on these angled faces, a doubled mouth on Layla at 25.4 s).
- Compositor fixes found in this pass (`tools/assemble_masked.py`):
  - Two zoomed jobs on the same shot (one per girl) were both matched to the first plan entry, so Layla's layer
    used Melody's speech windows. Each job now uses its own plan entry (its index is in the job name).
  - Where the mouth outline cannot be found for a few frames (a `steady` job), the neighbours' outlines are
    interpolated and moved with the detector's mouth corners, and the mask is a little wider.
  - Melody turns to full profile at 23.06–23.36 s: there neither the landmarks nor the mouth corners find her mouth,
    and sync-3's output differs from the original along her whole profile, so no mask can be trusted; that job is
    marked `fade_profile`: the lip sync fades out and back in over 3 frames there instead of flipping between
    mouths. (Layla's profile frames keep the lip sync: there the interpolated outline sits on her mouth.)
