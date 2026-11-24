# Melody EP101 — product placement demo (13 s)

Source: `Melody_EP101_H264_fragmento_v2.mp4`, 1:17.12–1:30.13 (frames 1849–2160, 312 frames, 13.01 s; starts on
the cut after the singer's close-up). Output: `Melody_EP101_product_placement.mp4` — same picture size, frame rate
and length, the original audio untouched (correlation with the source 0.9999, no offset).

## What the viewer sees

| Clip time | Picture | Top-left label |
|---|---|---|
| 0 – 4.7 s | original | ORIGINAL FOOTAGE · Product placement · before |
| 4.7 s (cut to the close shot) | the product photo drops onto his jacket on a card ("THE PRODUCT") | |
| 5.0 – 6.8 s | a gold line sweeps from the lower-left corner to the upper-right, BEFORE / AFTER tags on either side; it slows across his jacket, and the card is wiped into the real jacket | AI PRODUCT PLACEMENT · Product placement · after |
| 6.8 s – end | his green jacket is the white hooded jacket in every shot he is in | |

The Phatty Acid logo is top right throughout; the labels use the language demo's design (`tools/pp_labels.py`
reuses `tools/melody_labels.py`).

## How the jacket was replaced

1. **Seedance 2.5** (fal, `bytedance/seedance-2.5/us/reference-to-video`, `task: editing`, 1080p, high bitrate,
   no audio; `tools/pp_seedance.py`): the 8 s after the first 5 s (192 frames; re-tagged 23.976 → 24 fps, which the
   model requires) as @Video1 and the product photo as @Image1, with a prompt that keeps everything identical
   (faces, expressions, lips, motion, camera, cuts, crowd, light, grain) and changes only the grey-haired man's
   olive jacket into the jacket in @Image1, worn open the way he wears his own. Result: the right jacket (white
   perforated fabric, black zip and piping, branded hood tape, adidas logo on the left chest) in all three of his
   shots, the box shot without him untouched — but not frame-exact: 185 frames for 192, up to 6 frames (0.25 s)
   ahead, and his face slightly re-drawn.
2. **Only the jacket is taken from it** (`tools/pp_jacket_composite.py`), so his face, lips, hands, the bucket and
   the crowd stay the original pixels and stay in sync with the original audio:
   - masks: SAM 3 (fal `fal-ai/sam-3/video-rle`, `tools/pp_sam.py`) per shot — "green jacket" on the original,
     "white jacket" on the generated video, kept only where they lie on him (his whole-body mask from point prompts);
   - time: each original frame is matched to a generated frame (monotonic DTW, jackets flattened to grey so the
     colour change does not drive the match);
   - space: optical flow (DIS) from the original frame to its generated frame, jackets flattened, blurred in space
     and smoothed over ±4 frames (σ 2.5) so the warped jacket does not wobble; the generated frame is warped onto
     his original pose;
   - composite: inside (original jacket ∪ warped new jacket), 2 px feather, the warped generated pixels; everywhere
     else the original.
   Checks: jacket frame-to-frame change in the composite matches the generated video's own (close shot: 4.7 vs 3.3;
   unsmoothed flow gave 10.9 = visible jitter); no green left at the edges (collar, cuffs, around the bucket and hands
   checked at full size).
3. **Edit** (`tools/pp_render.py`): card, wipe, tags, labels, logo; original audio; x264 CRF 14.

## Files

- `outputs/pp/Melody_EP101_product_placement.mp4` — master (23 MB, 312 frames, 1920x1080, 24000/1001, AAC 320k).
- Working files in `work/pp/` (segment, Seedance output `gen/sd_a.mp4`, masks, composite `swap8_c.mkv`).

## Cost (fal)

One Seedance 2.5 run at 1080p (billed per token, roughly $8–16 for 8 s at 1080p) and 11 SAM 3 mask runs (under
$0.50). No fallback provider was needed.

---

# Version 2 — full-frame video-edit model (client: "the cropped jacket moves weirdly")

Output: `outputs/pp/Melody_EP101_product_placement_v2.mp4` (same edit, card, wipe, labels and original audio).
The jacket is no longer cut out and warped onto the original: the whole frame comes from a video-EDIT model (the
source video is the base and is kept; only the jacket is changed), so the jacket moves with his body natively.

Same 8 s input (original 23.976 fps, 192 frames), same product photo, one prompt for all models
(`tools/pp_edit_models.py`): replace only his olive jacket with the jacket in the image, worn open, hood down; keep
face, identity, expressions, eye and mouth/lip movement on every frame, motion and timing, bucket, other people,
background, camera, cuts, speed, light and grain identical. Compared with `tools/pp_eval_edits.py` against the
original (timing offset per shot in frames, + = late; face/background mean abs difference at 960x540, 0-255):

| Model (fal) | Frames | Offset per shot | Face diff | Background diff | Jacket | Verdict |
|---|---|---|---|---|---|---|
| Seedance 2.5 reference-to-video (v1) | 185 @ 24 | −1, −4, −5 | 24.5 | 14.7 | right | not frame-exact |
| **Kling O3 Pro video-to-video edit** | 193 @ 24 | **0, 0, 0** | **6.2** | **3.3** | logo, black piping, cuffs, hem; open in every shot | **used** |
| Kling 4.0 video-to-video edit | 193 @ 24 | 0, +1, +1 | 9.3 (6.0 after shifting) | 5.0 | perforated texture, hood tape; zipped up in the wide shot (continuity) | close second |
| Happy Horse video edit | 193 @ 24 | +2, +4, +8 | 32.3 | 17.5 | very good | changes his face; late |
| Wan 2.7 edit video | 240 @ 30 | −5, −6, 0 | 35.4 | 23.2 | — | drifts |

Kling O3 Pro's cuts fall on the original's frames (66, 113, 156), so its frames are used 1:1. The box shot he is not in
(frames 113–155 of the 8 s) is the original shot. Faces are about 20 % softer than the source (a full-frame re-render)
but the same face, expression and mouth on every frame; no flicker beyond the original's own motion.

Cost (fal): Kling O3 Pro ~$1.1, Kling 4.0 ~$1.3, Wan 2.7 ~$0.8, Happy Horse ~$1.1 (one server error, re-run).
