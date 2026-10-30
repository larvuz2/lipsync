# Test 1 results: first three clips (87434, 87646, 87725)

The archery scene: the trainer teaching Jankó. All three clips are dubbed into American English and
lip-synced. Finals keep the original file names (`deliverables/test1/EN/`, `.mp4` + `.mp3`).

## What each clip got

| Clip | On camera | What we did |
|---|---|---|
| 87434 | Trainer alone, profile → 3/4 | English line, mouth lip-synced (whole clip) |
| 87646 | Boy listening; trainer speaks **off-camera** | English audio only; picture untouched, so the boy's mouth doesn't move |
| 87725 | Shot 1 (frames 0–54): boy close-up, trainer off-camera. Shot 2 (55–219): wide, trainer visible | Shot 1 untouched; shot 2 lip-synced on the trainer's face only; spliced frame-exact |

## English script (ours)

| Clip | Hungarian | English |
|---|---|---|
| 87434 | Jankó, gyere ide! | Jankó… come here! |
| 87646 | Na, mutasd! / Hogy tartod azt az íjat? | Well, show me! / How are you holding your bow? |
| 87725 | Az ideget tartsd távolabb, megüti az arcod. / Engedd lejjebb a vállad. | Keep the string away, or it'll hit your face. / Lower your shoulder. |

Sync auto-dub (version A) translated on its own: "Yanko, come here." / "Now show me. How are you
holding that bow?" (Whisper hears "bowl"; check by ear) / "Hold the bow further out. It'll hit your face. Drop your shoulder." The third
line has a meaning error: *ideg* is the bow**string**, not the bow.

## Versions delivered

| Folder | Audio | Lip sync |
|---|---|---|
| `EN/` (main) | Ours: our translation, trainer's cloned voice (TTS), fitted to the actor's timing | sync-3 |
| `alt_A_autodub/` | Sync/ElevenLabs auto-dub of the scene (automatic translation + voice clone) | sync-3 |
| `alt_C_lipsync2pro/` (in the review reels) | Ours | lipsync-2-pro (cheaper model) |
| `review/` | `<clip>_compare.mp4`: HU original → ours → auto-dub → lipsync-2-pro; `scene_EN.mp4`: the three clips back to back | |

## Checks

- **Frame-exact:** every output has the source's frame count (92 / 79 / 220), 1920×1080, 23.976 fps.
  The 87725 splice was verified against the original at >50 dB PSNR on every untouched frame.
- **Right face:** only the trainer's face changed. The boy's face region is unchanged (max pixel
  change 7–13 of 255, i.e. encoding noise).
- **Lip timing:** in 87434 the mouth movement follows the English audio within 1 frame (~40 ms), and
  correlates with it more strongly (0.43) than the original mouth did with the Hungarian (0.27).
- **Words:** every English take was checked with Whisper: 30 of 30 word-perfect.
- **Level:** English dialogue matches the original dialogue loudness (within ~1 dB on speech).
- **Look:** close-ups show no seams, blur or skin-tone shifts. sync-3 redraws the whole lower face;
  lipsync-2-pro only a small mouth patch.

## Voice likeness (automatic speaker-ID score, ECAPA)

| Compared with the trainer's real Hungarian voice | Similarity |
|---|---|
| Same actor, his other clips (reference) | 0.48 |
| **Ours**: cloned voice + TTS | 0.47 |
| **Sync auto-dub** | **0.67** |
| Different actor (the father) | 0.26 |

Our clone sits in the same range as the actor against himself, well above a different person. The
auto-dub voice is closer still. Part of that may be that it re-voices the original performance
directly, so it keeps more of his delivery and recording character. A rough score: listen and decide.

## Cost

About $7.40 in usage: auto-dub $3.44, sync-3 $2.85 (two versions × 10.7 s), lipsync-2-pro $0.89,
30 TTS takes ≈ $0.20. One voice-clone slot used ("Raven S01 - Trainer (archery)").

## What to try next (to reach "perfect")

1. **Get the auto-dub's voice with our script.** Options: Sync's reviewed-dubbing flow (edit the
   auto-dub's English text, then regenerate in the same cloned voices), or clone the trainer from the
   auto-dub's English output and re-run our TTS. Then A/B again on the speaker score.
2. **More reference audio per character** (all their lines across the episode) for stronger clones.
3. **Native-speaker pass** on the Hungarian transcript and the English lines before locking.
4. **Scale-up:** same pipeline per scene; only on-camera lines get lip-synced (cheaper, and no wrong
   faces moving).
