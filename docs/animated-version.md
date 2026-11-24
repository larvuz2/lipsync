# Melody EP101 — animated version (section 4, 9.1 s)

Source: `Melody_EP101_H264_fragmento_v2.mp4`, 0:50.18–0:59.27 (frames 1203–1420, 218 frames): the radio-corner scene,
both girls talking ("¿Cómo me enoja que tengas que esconderte? Prométeme que algún día…" / "Algún día nada. Eso es
futuro y el futuro no existe. Mi presente es esto que vimos aquí y ahora."). Starts on the shot cut, ends before the next
line; no burned-in credits (the station two-shot was rejected because of the opening credits). Shots at clip frames
0, 62, 108, 150.

## Character sheets (`tools/anim_sheets.py`, fal Nano Banana Pro edit, 2K, 16:9)

From crops of the girls (face, upper body, full outfit from later scenes), each redesigned as a stylized 3D
animated-film character: full-body turnaround (front, ¾, side, back) and five expressions, every costume detail kept
(blonde: plaid shirt over grey tee, long cord necklace, black shorts, black buckle boots, braids; dark-haired: studded
black leather vest, orange floral top/skirt, pink watch, bracelets, hoops, gold platform sneakers). The dark-haired
girl's sheet was made first; the blonde's used it as the style reference so both match. Two variants each; used
`work/anim/sheets/layla_0.png` and `melody_0.png`.

## Restyle (`tools/anim_video.py`)

The clip plus both sheets (@Image1 blonde, @Image2 dark-haired), one prompt: same shots and cuts, camera, poses,
expressions and mouth movements frame by frame so the dialogue stays in sync; set restyled; no text; no audio.

| | Seedance 2.5 (editing, 1080p) | Kling O3 Pro video edit |
|---|---|---|
| Frames | 217 (24 fps), cuts at 62/108/150 | 217 (24 fps), cuts at 62/108/150 |
| Result | only the blonde animated; the dark-haired girl and the set stayed photoreal | both girls on-model with their sheets, set restyled (warmer light), mouths follow the original |
| | not used | **used** (last frame repeated to 218) |

## Edit (`tools/anim_render.py`) → `outputs/anim/Melody_EP101_animated_version.mp4`

0–3 s live action (label ORIGINAL FOOTAGE · Animated version · live action); the two character sheets pop up as cards
at 1.6 s; 3.0–4.35 s a gold vertical line sweeps right to left ("filter" wipe) with LIVE ACTION / ANIMATED tags;
label → AI ANIMATION STYLE · Animated version · 3D animated; cards fade by 4.9 s. Original audio (−21.3 LUFS).

Added to the reel as part 4 (`tools/final_assemble.py`; titles now 01–04 / 04; 2:11, 3135 frames).
Cost (fal): sheets 4 × $0.15; Seedance ~$8 (1080p); Kling O3 Pro ~$1.3.
