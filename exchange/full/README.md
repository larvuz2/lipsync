# Full sequence run (winner recipe: Sync auto-dub + sync-3)

Source: Drive folder "LIP SYNC TEST" (58 clips, Splits00087434 … Splits00110020), episode order = split number.

Helper session (has SYNC_API_KEY):

    rm -rf media && pip install -q gdown && python3 tools/fetch_drive.py
    ln -sfn "LIP SYNC TEST" media/full          # media/full/*.mp4
    python3 tools/full_stage.py dub exchange/full       # step 1 (~$37.50)
    python3 tools/full_stage.py lipsync exchange/full   # step 2, after lipsync_jobs.json is committed

clips.json lists every clip with its frame count; the scripts refuse a clip whose frame count differs
(old test downloads share file names with different content).
