from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DB_PATH, LOGS_DIR, ensure_dirs

STATUSES = ("queued", "running", "done", "failed")
SOURCE_TYPES = ("upload", "url")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'upload',
    source_url TEXT,
    source_path TEXT,
    filename TEXT NOT NULL DEFAULT '',
    language TEXT,
    transcript_source TEXT NOT NULL DEFAULT 'auto',
    transcript_used TEXT,
    pad_start REAL NOT NULL DEFAULT 2.0,
    pad_end REAL NOT NULL DEFAULT 5.0,
    reencode INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    window_json TEXT,
    output_path TEXT
)
"""

COLUMNS = (
    "id",
    "status",
    "source_type",
    "source_url",
    "source_path",
    "filename",
    "language",
    "transcript_source",
    "transcript_used",
    "pad_start",
    "pad_end",
    "reencode",
    "title",
    "created_at",
    "started_at",
    "finished_at",
    "error",
    "window_json",
    "output_path",
)

# The first schema only handled uploads, under a different column name.
RENAMED_FROM = {"source_path": "upload_path"}


def _utc_now() -> str:
    """Sub-second precision keeps job ordering stable within the same second."""
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Rebuild the table when it has an older shape; SQLite cannot rename or drop in place."""
    current = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    if current == set(COLUMNS):
        return

    conn.execute("DROP TABLE IF EXISTS jobs_old")
    conn.execute("ALTER TABLE jobs RENAME TO jobs_old")
    conn.execute(SCHEMA)
    kept = [c for c in COLUMNS if c in current or RENAMED_FROM.get(c) in current]
    source = [c if c in current else RENAMED_FROM[c] for c in kept]
    conn.execute(
        f"INSERT INTO jobs ({', '.join(kept)}) SELECT {', '.join(source)} FROM jobs_old"
    )
    conn.execute("DROP TABLE jobs_old")


@dataclass
class Job:
    id: str
    status: str
    source_type: str
    source_url: str | None
    source_path: str | None
    filename: str
    language: str | None
    transcript_source: str
    transcript_used: str | None
    pad_start: float
    pad_end: float
    reencode: bool
    title: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    window_json: str | None
    output_path: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Job":
        return cls(
            id=row["id"],
            status=row["status"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            source_path=row["source_path"],
            filename=row["filename"],
            language=row["language"],
            transcript_source=row["transcript_source"],
            transcript_used=row["transcript_used"],
            pad_start=float(row["pad_start"]),
            pad_end=float(row["pad_end"]),
            reencode=bool(row["reencode"]),
            title=row["title"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error=row["error"],
            window_json=row["window_json"],
            output_path=row["output_path"],
        )

    @property
    def display_title(self) -> str:
        return (self.title or "").strip() or self.filename or self.source_url or self.id

    @property
    def source_label(self) -> str:
        return self.source_url if self.source_type == "url" else self.filename

    @property
    def created_label(self) -> str:
        stamp = re.sub(r"\.\d+", "", self.created_at.replace("T", " "))
        return stamp.replace("+00:00", " UTC").strip()

    @property
    def window(self) -> dict[str, Any] | None:
        if not self.window_json:
            return None
        try:
            data = json.loads(self.window_json)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    @property
    def is_active(self) -> bool:
        return self.status in {"queued", "running"}

    @property
    def output_exists(self) -> bool:
        return bool(self.output_path) and Path(self.output_path).is_file()

    @property
    def download_name(self) -> str:
        stem = Path(self.filename).stem if self.filename else ""
        base = stem or _slug(self.display_title) or self.id
        return f"{base}_sermon.mp4"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\- ]+", "", value).strip()
    return re.sub(r"[\s_]+", "_", cleaned)[:80]


def create_job(
    *,
    job_id: str,
    source_type: str,
    filename: str = "",
    source_path: Path | None = None,
    source_url: str | None = None,
    language: str | None,
    transcript_source: str,
    pad_start: float,
    pad_end: float,
    reencode: bool,
) -> Job:
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"Unknown source type: {source_type}")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, status, source_type, source_url, source_path, filename,
                language, transcript_source, pad_start, pad_end,
                reencode, created_at
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                source_type,
                source_url,
                str(source_path) if source_path else None,
                filename,
                language,
                transcript_source,
                pad_start,
                pad_end,
                int(reencode),
                _utc_now(),
            ),
        )
    job = get_job(job_id)
    if job is None:
        raise RuntimeError("Failed to create job")
    return job


def get_job(job_id: str) -> Job | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return Job.from_row(row) if row else None


def list_jobs(limit: int = 100) -> list[Job]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [Job.from_row(row) for row in rows]


def claim_next_job() -> Job | None:
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            UPDATE jobs
            SET status = 'running', started_at = ?, error = NULL
            WHERE id = ? AND status = 'queued'
            """,
            (_utc_now(), row["id"]),
        )
    return get_job(row["id"])


def mark_done(
    job_id: str,
    *,
    window: dict[str, Any],
    output_path: Path,
    title: str | None,
    transcript_used: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'done',
                finished_at = ?,
                window_json = ?,
                output_path = ?,
                title = COALESCE(?, title),
                transcript_used = ?,
                error = NULL
            WHERE id = ?
            """,
            (
                _utc_now(),
                json.dumps(window, ensure_ascii=False),
                str(output_path),
                title,
                transcript_used,
                job_id,
            ),
        )


def mark_failed(job_id: str, error: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'failed', finished_at = ?, error = ?
            WHERE id = ?
            """,
            (_utc_now(), error[:4000], job_id),
        )


def requeue_stale_running() -> int:
    """Any 'running' job belongs to a dead worker after a restart."""
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE jobs
            SET status = 'queued', started_at = NULL
            WHERE status = 'running'
            """
        )
        return cur.rowcount


def log_path(job_id: str) -> Path:
    return LOGS_DIR / f"{job_id}.log"


def read_log(job_id: str, max_bytes: int = 64_000) -> str:
    path = log_path(job_id)
    if not path.is_file():
        return ""
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[-max_bytes:]
        text = data.decode("utf-8", errors="replace")
        return "… (truncated)\n" + text
    return data.decode("utf-8", errors="replace")
