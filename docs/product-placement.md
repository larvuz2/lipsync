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
