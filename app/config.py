from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).expanduser().resolve()
DB_PATH = DATA_DIR / "app.db"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
WORK_DIR = DATA_DIR / "work"
LOGS_DIR = DATA_DIR / "logs"
ASSETS_DIR = DATA_DIR / "assets"

ALLOWED_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi"}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024 * 1024)))
WORKER_POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "2"))
CHANNEL_POLL_SECONDS = float(os.environ.get("CHANNEL_POLL_SECONDS", "900"))
CHANNEL_RECENT_VIDEOS = int(os.environ.get("CHANNEL_RECENT_VIDEOS", "20"))


def dashboard_credentials() -> tuple[str, str]:
    user = os.environ.get("DASHBOARD_USER", "").strip()
    password = os.environ.get("DASHBOARD_PASSWORD", "").strip()
    return user, password


def ensure_dirs() -> None:
    for path in (DATA_DIR, UPLOADS_DIR, OUTPUTS_DIR, WORK_DIR, LOGS_DIR, ASSETS_DIR):
        path.mkdir(parents=True, exist_ok=True)
