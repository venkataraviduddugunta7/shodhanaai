import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_DATA_DIR = ROOT / "data"
DATA_DIR = Path(os.environ.get("SHODHANA_DATA_DIR", str(REPO_DATA_DIR))).expanduser()
SEED_DIR = DATA_DIR / "seed"
UPLOAD_DIR = DATA_DIR / "uploads"
SAMPLES_DIR = REPO_DATA_DIR / "samples"
WEB_DIR = ROOT / "web"
DB_PATH = DATA_DIR / "shodhana_duloxetine.sqlite3"
SAMPLE_XLSX = SAMPLES_DIR / "duloxetine_sample.xlsx"


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
