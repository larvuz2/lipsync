"""Download the shared Drive test folder into media/ (git-ignored).

    pip install gdown
    python3 tools/fetch_drive.py
"""
import sys
from pathlib import Path

from gdown.download_folder import download_folder

FOLDER = "https://drive.google.com/drive/folders/10425y78ckeKRs6ogoAL4S7pSQEgeM290"
out = Path(__file__).resolve().parent.parent / "media"
out.mkdir(exist_ok=True)
files = download_folder(url=sys.argv[1] if len(sys.argv) > 1 else FOLDER, output=str(out) + "/",
                        quiet=False, resume=True)
print(f"{len(files or [])} files in {out}")
