# sync. labs — notes for this project

Condensed from https://sync.so/docs (read 2026-10-30) and the public OpenAPI spec
(https://sync.so/docs/openapi.json). Only the parts that matter for dubbing
*Rise of the Raven* from Hungarian into American English.

## Basics

- Base URL `https://api.sync.so`, all endpoints under `/v2`.
- Auth: header `x-api-key: <key>`. The Python SDK (`pip install syncsdk`, `from sync import Sync`)
  and TS SDK (`@sync.so/sdk`) read the key from the `SYNC_API_KEY` environment variable.
- Everything is asynchronous: submit a job, then poll `GET /v2/generate/{id}` until
  `COMPLETED` / `FAILED` / `REJECTED` (or pass `webhookUrl`).
- Cost check before submitting: `POST /v2/generations/estimate` (lip sync) and
  `POST /v2/integrations/dubbing/estimate` (dubbing audio).

## Models (lip sync)

| Model | Use | Price at 25 fps (Creator → Scale) |
|---|---|---|
| `sync-3` | Best. Whole-shot processing, 4K, handles profiles, close-ups, hands/hair over the mouth, keeps emotion. Can open "silent" lips. | $0.133 → $0.107 /s |
| `lipsync-2-pro` | 512px face, extra detail on teeth and beards. Processes in 2 s chunks. Weaker on angles. | $0.083 → $0.067 /s |
| `lipsync-2` | Cheaper general model. | $0.05 → $0.04 /s |
| `react-1` | Adds expressions and head motion. 15 s max. Not useful for dubbing finished footage. | $0.167 /s |

sync-3 ignores `temperature`, `reasoning_enabled`, `occlusion_detection_enabled` (built in).

## Ways to get English audio

1. **One-call dubbing**: `POST /v2/generate` with only the video input plus
   `dubParams: { providerName: "elevenlabs", sourceLang: "hu", targetLang: "en-US" }`.
   Sync extracts the audio, ElevenLabs Dubbing v2 detects speakers, clones each voice, translates,
   keeps the background, then the lip-sync model runs on the result. No control over wording or timing.
   Dubbing audio is billed separately: $0.10/s (Creator), $0.08/s (Scale).
2. **Dubbing audio only**: `POST /v2/integrations/dubbing` (`sourceAudioUrl` or `audioAssetId`,
   `targetLang`, `sourceLang`, `cloningStrength` 1–10, Studio default 7). Lets us listen and fix the
   English audio before paying for lip sync.
3. **Manual pipeline** (full control):
   - `POST /v2/transcriptions` — word timings plus speaker info, free.
   - Translate ourselves (lip-sync-aware, timed to each line).
   - `POST /v2/voices` — clone from an asset in Sync storage (audio or video; first 2 min used;
     up to 10 `sampleUrls`). Returns `voiceId`. Delete with `DELETE /v2/voices/{id}` to free a slot.
   - `POST /v2/tts` — `{ script, voiceId, provider: "elevenlabs", stability, similarityBoost }`,
     max 5000 chars, 60 req/min, ~$0.004/s. Has no speed control, so we time-fit locally.
   - `POST /v2/generate` with video plus the English audio.

## Inputs and limits

- Media must be a public URL or uploaded into Sync storage:
  `POST /v2/assets/upload` (presigned PUT), then `POST /v2/assets` → `assetId`.
  Voice-clone sources **must** be in Sync storage.
- Video: MP4/MOV/WebM/AVI, ≤ 4096×2160, constant 24/25/30 fps recommended, SDR. HDR is squashed to SDR.
- Audio: WAV/MP3 preferred, 44.1/48 kHz, only the first audio stream is used.
- Output is always re-encoded H.264 (`-crf 17 -preset slow`), RGB pipeline. For colour-critical
  work send BT.709-tagged `yuv444p`.

## Duration handling (`options.sync_mode`)

`cut_off` (min of the two), `silence` (pads, keeps full video), `remap` (time-stretches video),
`bounce`/`loop` (extend video). **Default is `bounce`.** For dubbing we want the output to be
exactly the source length, so we send English audio of the *same* length as the clip and use
`cut_off`.

## Choosing the face

- `options.active_speaker_detection`: `{ auto_detect: true }`, or `{ frame_number, coordinates: [x, y] }`
  (pixel coordinates on that frame), or per-frame `bounding_boxes` / `bounding_boxes_url`.
- `segments[]`: different audio per time range, each with its own `optionsOverride.active_speaker_detection`.
  **Caution:** each segment window stretches to fit its audio, so the output can be longer than the source.
- `speakers[]` (sync-3 only, needs `multispeaker_enabled` on the account, default max 3): several
  faces lip-synced on one timeline, each with a full-length audio track. Can't be combined with
  segments, `sync_mode`, dubbing, or global speaker selection. Good fit for two-shots if Sync
  enables it for us.

## Plans (what blocks what)

| Plan | $/mo | Max clip | Concurrent | Voice clones | Watermark |
|---|---|---|---|---|---|
| Free | 0 | 15 s, 3 videos/mo | 1 | 0 | yes |
| Hobbyist | 5 | 1 min | 1 | 3 | yes |
| Creator | 19 | 5 min | 3 | 5 | no |
| Growth | 49 | 10 min | 6 | 15 | no |
| Scale | 249 | 30 min | 15 | 50 | no (+ Batch API, −20 % usage) |

Free tier: 10 TTS/dubbing audio jobs a month (max 3 dubs, 20 s each).
