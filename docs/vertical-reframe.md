# Melody EP101 — vertical reframe demo (phase 3, 15 s)

Source: `Melody_EP101_H264_fragmento_v2.mp4`, 1:39.81–1:54.82 (frames 2393–2752, 360 frames, 15.015 s). Requested
1:40–1:55; it ends on the cut at 1:54.82 (instead of 4 frames into the next shot) and starts 0.19 s earlier to keep 15 s.
Shots (clip frames): 0–31 man with the box (wide), 32–72 low angle, 73–88 the girls at the mic, 89–179 the man in
green rushes in, 180–262 man with the box in the crowd, 263–359 the girls behind the newspaper stacks.

## Outputs

- `outputs/vr/Melody_EP101_vertical_reframe_demo.mp4` — landscape 1920x1080 demo, original audio:
  0–5 s original; 5.0–5.8 s a gold 9:16 frame appears and the landscape shrinks into the band it occupies in the
  vertical; 5.8–6.6 s the AI-extended picture grows out above and below (gold edges), with "ORIGINAL 16:9" and
  "AI EXTENDED" tags until 8.2 s; then the vertical plays centred, black at the sides. Top-left label (Melody design):
  ORIGINAL FOOTAGE · Vertical reframe · 16:9 → AI REFRAME FOR SOCIAL · Vertical reframe · 9:16; logo top right.
  (`tools/vr_render.py`)
- `outputs/vr/Melody_EP101_vertical_9x16.mp4` — the vertical itself, 1080x1920, 360 frames, original audio.

## How

The whole 16:9 picture is kept (fitted across the width, 1080 x 607.5, centred) and the canvas above and below is
generated. Two fal reframe models, same 15 s, a prompt describing the station and every character's clothes to be
continued exactly (neither model takes reference images) — `tools/vr_reframe.py`:

| | Luma Ray 3.2 Reframe | MiniMax H3 Max Reframe Video |
|---|---|---|
| Output | 720x1280 (1080p not offered for 9:16), two 7.5 s calls split at the cut (10 s limit) | 1080x1920 (upscaled from 768p), one call |
| Timing | 0 frames off in all 6 shots | 0 frames off in all 6 shots |
| Original picture in the band | kept (diff 5.6/255) | re-rendered (diff 10.1): faces changed, the girls' faces melted in the newspaper shot |
| Continuity of the extension | good; drops the hand truck under the box in the crowd shot | better: box stays on its hand truck, the orange floral dress and shorts continue, same set |

Used: MiniMax's extension (continuity, 1080x1920) with the band replaced by the original footage (`tools/vr_band.py`:
resized to 1080 x 607.5 at y 656.25, 14 px blend at the band's top and bottom edges). The model's band is aligned with
the original (no offset, colour shift < 1/255), so bodies, box and shoes run straight across the edges; checked on
close-ups and frame by frame (the step across each edge is no larger than in neighbouring rows). Faces, mouths and
clothes inside the band are the original pixels.

Cost (fal): Luma ~$0.45 (15 s), MiniMax ~$0.75; under $1.50 in total.
