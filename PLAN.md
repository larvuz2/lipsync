# Rise of the Raven: Hungarian → American English dub with lip sync

Goal: dub the show into American English, keep each actor's voice (cloned),
and make the mouths match the English. First milestone: **3 test clips** that
look and sound right, before running anything at scale.

---

## 1. Where the API key goes

Don't paste keys into chat or commit them to git.

**Claude Code on the web (this environment):**
1. Open the cloud environment menu in the session's title bar and choose **Edit**.
2. Add an environment variable `SYNC_API_KEY=<your key>`. Put it in the same place `FAL_KEY` is
   already set (or under *Network secrets* / *API credentials*, if your settings page shows that section).
3. Start a new session (or ask me to continue in one). New sessions pick up the variable.
4. I run `python3 tools/sync_api.py check`. It makes a free call that confirms the key works and
   lists the models your plan can use.

**Running locally:** copy `.env.example` to `.env` and fill it in. `.env` is git-ignored.

You don't need an ElevenLabs key. Sync's dubbing, voice cloning and TTS run on ElevenLabs through
Sync's own account. (Optional: you can connect your own ElevenLabs key in Sync, and ElevenLabs then
bills you directly for dubbing audio.)

---

## 2. What's in the Drive folder

`LIP SYNC TEST/` holds 17 clips from **S01E01**, about 85 s in total. Each clip comes as an
`.mp4` plus an `.mp3`. Full table: [`docs/clip-inventory.md`](docs/clip-inventory.md).

- Video: 1920×1080 H.264, **23.976 fps**, 1.5–9.5 s per clip.
- Each `.mp3` is the **same audio** as its `.mp4` (99.9 % match, 47 ms encoder offset). It is the
  **final mix**: Hungarian dialogue plus music and sound effects. No clean voice track.
- **No `.wav` file** is in the shared folder. The WAV you mentioned (the full conversation audio)
  hasn't been shared yet, or sits somewhere the link doesn't cover.
- The file names say the masters are `ProRes4444_2160p25 … OV20 / MNE20 / OV51 / MNE51`: 4K ProRes
  4444 at **25 fps**, with a separate **M&E** (music & effects, no dialogue) track in stereo and 5.1.
  These test clips are 1080p 23.976 proxies of that.

---

## 3. What Sync gives us (short version)

Details and endpoint notes: [`docs/sync-docs-notes.md`](docs/sync-docs-notes.md).

- **Lip-sync model: `sync-3`.** It's Sync's model built for profiles, close-ups, hands or hair
  over the mouth, and whole-shot consistency, and this show is full of exactly those shots.
  `lipsync-2-pro` costs about 40 % less but is weak on angles. We test both once.
- **English audio, two ways:**
  - **One-call dubbing** (`dubParams`, `hu` → `en-US`): ElevenLabs detects the speakers, clones
    each voice, translates, keeps the background, and Sync lip-syncs. Fast, but we can't control the
    wording or timing.
  - **Our own pipeline:** transcribe → lip-sync-aware translation → clone each character's voice
    (`/v2/voices`) → TTS in that voice (`/v2/tts`) → fit each line to the Hungarian line's exact
    timing → lip-sync. More steps, but we control every line.
- **Picking the face:** `active_speaker_detection` (a point on the face, or a box per frame). For
  two people talking in one shot, sync-3 has a `speakers` mode (needs Sync to enable it on the account).
- **Plan matters:** the Free plan has **0 voice clones** and a watermark. **Creator ($19/mo)** is
  the minimum for real tests: 5 clones, no watermark, 5-min clips. The full show will need more clone
  slots: Growth (15) or Scale (50, −20 % usage, Batch API).

---

## 4. What makes "perfect" lip sync hard here

1. **Timing.** The English line has to start and stop where the Hungarian mouth moves and pause
   where it pauses. We translate to match syllable count and phrasing, then stretch or squeeze the
   TTS by up to about ±10 % to land exactly on the original timing. The output must be frame-for-frame
   the same length as the source so it drops back into the edit.
2. **Off-screen voices.** In dialogue scenes the person talking is often *not* the one on camera.
   Lip-syncing the visible listener would be wrong. Every line gets tagged "on screen" or
   "off screen", and only on-screen lines are lip-synced.
3. **Voice-clone quality.** In these clips each character speaks for only a few seconds, which is
   too little for a good clone (aim for 1–2 minutes of clean speech). More audio per character
   (e.g. the whole episode), ideally as a **dialogue-only stem**, fixes this.
4. **Music and effects.** The audio we have is a full mix. For the English version we need the
   background without Hungarian dialogue. The production's **M&E track** is the clean answer.
   AI separation (Demucs or ElevenLabs) is the fallback and leaves some artifacts.
5. **Frame rate and resolution.** The proxies are 23.976 fps and the masters 25 fps. Final renders
   must run on the delivery master (or a frame-exact copy), or the sync drifts when conformed.
   Sync accepts up to 4096×2160, so 4K masters work. Send 4:4:4 BT.709 to avoid colour shifts.
6. **Cuts inside a clip.** Several "splits" contain more than one shot. sync-3 works per shot, so
   we split at the cuts before lip-syncing and rejoin afterwards.

---

## 5. The tests

### The three test clips (20.8 s total)

| # | Clip | What's in it | Why it's a good test |
|---|---|---|---|
| 1 | **87434** (3.9 s) | Trainer, alone in frame, head turning from profile to 3/4. One line: *"Jankó, gyere ide!"* | Simplest real case: one face, one voice, tricky angle. |
| 2 | **90058** (9.5 s) | Father frontal (2 lines) → group shot (father's 3rd line) → boy close-up (*"Én maradok veled!"*) → off-screen *"Jankó!"* | A real dialogue moment: 3 shots, 2 cloned voices, and lines that must be lip-synced, voice-only, or both. |
| 3 | **88011** (7.4 s) | Extreme close-up, trainer and boy cheek to cheek, trainer's mouth partly behind the boy's hand. *"Ne a kezeddel célozz, ne is a szemeddel."* | Hardest kind of shot in the show: two faces, partial face, something in front of the mouth. Easy for the model to animate the wrong face. |

### Test A: one-call dubbing (baseline)
One request per clip: `dubParams` (`hu` → `en-US`) + `sync-3` + face selection for clips 2 and 3.
Sync and ElevenLabs do everything: speakers, voice clones, translation, background, lip sync.
This shows what "out of the box" looks like with no work from us. Expect trouble on clip 2:
one request can only target one face, and that clip has two on-screen speakers across three shots.

### Test B: our controlled pipeline (likely production candidate)
1. **Clean dialogue.** Best: the production's M&E and dialogue stems. Fallback: an AI separation
   model. The official Demucs weights won't download from this environment (Meta's server returns
   Access Denied), so we'd use another vetted separation model, or let ElevenLabs separate the
   audio as it does in Test A.
2. **Line sheet.** Each line gets its start and end time, the speaker, and on-screen or off-screen
   (from the transcript, cross-checked with Sync's free `/v2/transcriptions`).
3. **Lip-sync-aware translation.** Match the syllable count and pauses so the English fits the
   Hungarian mouth movements. Drafts:

   | Clip | Time | Hungarian (syll.) | English draft (syll.) |
   |---|---|---|---|
   | 87434 | 0.00–2.64 | *Jankó, gyere ide!* (6) | Jankó, come over here! (6) |
   | 88011 | 0.00–1.70 | *Ne a kezeddel célozz,* (7) | Don't you aim using your hand, (7) |
   | 88011 | 1.86–4.66 | *ne is a szemeddel.* (6) | not even with your eyes. (6) |
   | 90058 | 0.00–0.92 | *Szedd a lábad!* (4) | Pick up your feet! (4) |
   | 90058 | 1.26–4.02 | *Ide figyeljetek! El kell bújnotok!* (11) | Listen to me, all of you! You have to hide! (11) |
   | 90058 | 4.18–7.74 | *Bármi történik, azt teszitek, amit anyátok mond, megértettétek?* (20) | Whatever happens, you do exactly what your mother tells you, understood? (19) |
   | 90058 | 7.90–8.92 | *Én maradok veled!* (6) | I'm staying here with you! (6) |
   | 90058 | 8.94–9.30 | *Jankó!* (2) | Jankó! (2) |

   The Hungarian comes from Whisper and needs a native speaker's check before we lock any line.

4. **Voice clones** (`/v2/voices`) for the trainer, the father and the boy, built from the cleaned
   dialogue (every second of each character we have). This uses 3 clone slots.
5. **TTS** each line in its cloned voice (`/v2/tts`). Then time-fit it to the exact Hungarian window
   (at most ±10 %; if it needs more, rewrite the line instead of stretching it).
6. **Rebuild the audio.** Make one full-length English dialogue track per clip, mixed over the
   music-and-effects background, so the length matches the source exactly.
7. **Lip sync** with `sync-3` and `sync_mode: cut_off`, with the face picked by a point on the
   speaker. Run per shot (split at the cuts), and only on shots where the speaker is visible.
   Off-screen lines get audio only.
8. **Check.** Frame count matches the source, and the clip goes into a side-by-side review.

### Test C: model check
Run Test B's English audio through `lipsync-2-pro` as well (about 40 % cheaper) and compare it with
`sync-3`. This decides the model for the full run. Optional: since `FAL_KEY` is already set, also
run the same audio through one FAL-hosted lip-sync model as an outside reference.

### How we judge "perfect"
For each clip you get: the original | Test A | Test B side by side, a slowed-down close-up of the
mouth, and a short score sheet. A clip passes when:
- there's no visible lag (within 1 frame),
- there are no mouth artifacts at full size,
- the voice reads as the same actor,
- the English sounds natural,
- the output is exactly as long as the source.

### Cost of the tests
About 21 s of footage. sync-3 costs ~$2.80 per pass, one-call dubbing audio ~$2.10, TTS a few
cents, lipsync-2-pro ~$1.70. With a couple of retakes that's **about $10–15 in usage**, on top of
the plan fee (Creator is $19/mo).

For scale later: lip-syncing *every* second of a 60-minute episode with sync-3 would cost about
$480 at Creator rates ($385 on Scale). In practice only shots with a visible speaker need it.
The audio is cheap with our own TTS route (~$15/hour). One-call dubbing audio is $0.10/s
(~$360/hour).

---

## 6. What I need from you

1. `SYNC_API_KEY` added to the environment (section 1), and **which Sync plan** it's on.
2. The **WAV**: put it in the Drive folder (or tell me where it is). If it's just these 17 clips
   joined together, we already have that audio. For cloning, what helps is **more speech per
   character**: ~1–2 minutes each, e.g. the full episode's audio. I'll find each character's lines
   automatically.
3. If the production can provide them: the **M&E stem** and a **dialogue-only stem** for S01E01.
   That's the biggest single quality win: clean voices to clone, and a clean background for the
   English mix.
4. Character names for the people in the test clips, so voices and files are labelled properly.
   Also: keep the Hungarian names as spoken (e.g. "Jankó"), which is better for lip sync, or anglicize them?
5. Voice-clone consent: make sure the actors' contracts cover AI voice cloning for the dub. Sync and
   ElevenLabs terms require it.

---

## 7. Order of work

1. You add the key → I run `tools/sync_api.py check` (free).
2. Prepare Test B inputs locally (cleaned dialogue, line sheet, translations, timing). No cost.
3. Run Test A on the 3 clips → review.
4. Run Test B (+ C) on the 3 clips → side-by-side review with you.
5. Lock the recipe (model, translation style, voice settings). Then run one full scene, then one
   full episode, before batching the series.
