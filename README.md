# lipsync: Rise of the Raven, HU → EN-US dub

Dub the show from Hungarian into American English with cloned actor voices and lip sync,
using [sync. labs](https://sync.so/docs).

- **[PLAN.md](PLAN.md)**: where the API key goes, findings, the 3-clip test plan, open questions.
- [docs/clip-inventory.md](docs/clip-inventory.md): every test clip, who speaks, what's said, what to lip-sync.
- [docs/sync-docs-notes.md](docs/sync-docs-notes.md): the parts of the Sync docs that matter here.
- `tools/`: `fetch_drive.py` (get the clips), `transcribe_hu.py` (Whisper), `sync_api.py` (Sync API helper).
- `data/transcript_hu_whisper.json`: Hungarian transcript with word timings (needs a native-speaker check).

Media stays out of git (`media/`, `*.mp4`, `*.wav`…). Keys live in environment variables, never in the repo.
