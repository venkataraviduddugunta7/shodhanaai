from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
UPLOAD_DIR = DATA_DIR / "uploads"
SAMPLES_DIR = DATA_DIR / "samples"
WEB_DIR = ROOT / "web"
DB_PATH = DATA_DIR / "shodhana_duloxetine.sqlite3"
SAMPLE_XLSX = SAMPLES_DIR / "duloxetine_sample.xlsx"
CHEMDOZE_LOGIN_URL = "https://chemdoze.com/login"
CHEMDOZE_SEARCH_URL = "https://chemdoze.com/search"
CHEMDOZE_DOWNLOAD_EXCEL_URL = "https://chemdoze.com/download-excel"
CHEMDOZE_DOWNLOAD_PROGRESS_URL = "https://chemdoze.com/download-progress"
CHEMDOZE_DOWNLOAD_FILE_URL = "https://chemdoze.com/download-file"
CHEMDOZE_DEFAULT_QUERY = "Duloxetine"
CHEMDOZE_DEFAULT_FROM_DATE = "01/01/2020"
CHEMDOZE_DEFAULT_TO_DATE = "28/02/2026"
CHEMDOZE_CHAPTERS = [
    "4", "12", "13", "21", "23", "27", "28", "29", "30", "31",
    "32", "33", "34", "35", "38", "39", "90",
]


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
