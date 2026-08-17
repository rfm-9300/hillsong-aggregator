from __future__ import annotations

import re
import sqlite3
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import CHANNEL_POLL_SECONDS, CHANNEL_RECENT_VIDEOS
from app.jobs import connect, init_db
from app.settings import apply as apply_settings
from sermon_cut.pipeline import TRANSCRIPT_SOURCES
from sermon_cut.youtube import (
    ChannelSnapshot,
    ChannelVideo,
    DownloadError,
    is_channel_url,
    probe_channel,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS watch_channels (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    channel_id TEXT,
    title TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    language TEXT,
    transcript_source TEXT NOT NULL DEFAULT 'auto',
    pad_start REAL NOT NULL DEFAULT 2.0,
    pad_end REAL NOT NULL DEFAULT 5.0,
    reencode INTEGER NOT NULL DEFAULT 0,
    min_duration REAL NOT NULL DEFAULT 180.0,
    last_checked_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watch_videos (
    channel_pk TEXT NOT NULL,
    video_id TEXT NOT NULL,
    title TEXT,
    url TEXT NOT NULL,
    duration REAL,
    seen_at TEXT NOT NULL,
    job_id TEXT,
    skip_reason TEXT,
    PRIMARY KEY (channel_pk, video_id)
);
CREATE INDEX IF NOT EXISTS idx_watch_videos_seen ON watch_videos(seen_at DESC);
"""

_poll_lock = threading.Lock()
_monitor_lock = threading.Lock()
_monitor_started = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_watch_db() -> None:
    init_db()
    with connect() as conn:
        conn.executescript(SCHEMA)


@dataclass
class WatchChannel:
    id: str
    url: str
    channel_id: str | None
    title: str | None
    enabled: bool
    language: str | None
    transcript_source: str
    pad_start: float
    pad_end: float
    reencode: bool
    min_duration: float
    last_checked_at: str | None
    last_error: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "WatchChannel":
        return cls(
            id=row["id"],
            url=row["url"],
            channel_id=row["channel_id"],
            title=row["title"],
            enabled=bool(row["enabled"]),
            language=row["language"],
            transcript_source=row["transcript_source"],
            pad_start=float(row["pad_start"]),
            pad_end=float(row["pad_end"]),
            reencode=bool(row["reencode"]),
            min_duration=float(row["min_duration"]),
            last_checked_at=row["last_checked_at"],
            last_error=row["last_error"],
            created_at=row["created_at"],
        )

    @property
    def display_title(self) -> str:
        return (self.title or "").strip() or self.url

    @property
    def checked_label(self) -> str:
        if not self.last_checked_at:
            return "Never"
        stamp = re.sub(r"\.\d+", "", self.last_checked_at.replace("T", " "))
        return stamp.replace("+00:00", " UTC").strip()


@dataclass
class WatchDiscovery:
    channel_title: str
    video_id: str
    title: str
    url: str
    seen_at: str
    job_id: str | None
    skip_reason: str | None
    job_status: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "WatchDiscovery":
        return cls(
            channel_title=row["channel_title"] or "",
            video_id=row["video_id"],
            title=row["title"] or row["video_id"],
            url=row["url"],
            seen_at=row["seen_at"],
            job_id=row["job_id"],
            skip_reason=row["skip_reason"],
            job_status=row["job_status"],
        )

    @property
    def seen_label(self) -> str:
        stamp = re.sub(r"\.\d+", "", self.seen_at.replace("T", " "))
        return stamp.replace("+00:00", " UTC").strip()


@dataclass
class PollResult:
    checked: int = 0
    queued: int = 0
    errors: list[str] | None = None
    busy: bool = False
    message: str | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def list_channels() -> list[WatchChannel]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM watch_channels ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [WatchChannel.from_row(row) for row in rows]


def get_channel(channel_pk: str) -> WatchChannel | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM watch_channels WHERE id = ?", (channel_pk,)
        ).fetchone()
    return WatchChannel.from_row(row) if row else None


def list_discoveries(limit: int = 40) -> list[WatchDiscovery]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                cv.video_id, cv.title, cv.url, cv.seen_at, cv.job_id, cv.skip_reason,
                c.title AS channel_title,
                j.status AS job_status
            FROM watch_videos cv
            JOIN watch_channels c ON c.id = cv.channel_pk
            LEFT JOIN jobs j ON j.id = cv.job_id
            WHERE cv.job_id IS NOT NULL
            ORDER BY cv.seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [WatchDiscovery.from_row(row) for row in rows]


def enabled_count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM watch_channels WHERE enabled = 1"
        ).fetchone()
    return int(row["n"] if row else 0)


def add_channel(
    *,
    url: str,
    language: str | None,
    transcript_source: str,
    pad_start: float,
    pad_end: float,
    reencode: bool,
    min_duration: float,
) -> WatchChannel:
    url = url.strip()
    if not is_channel_url(url):
        raise ValueError(
            "Paste a channel URL such as https://www.youtube.com/@handle, not a video link."
        )
    if transcript_source not in TRANSCRIPT_SOURCES:
        transcript_source = "auto"

    apply_settings()
    try:
        snapshot = probe_channel(url, recent=CHANNEL_RECENT_VIDEOS)
    except DownloadError as exc:
        raise ValueError(str(exc)) from exc
    if snapshot.channel_id:
        existing = _find_by_channel_id(snapshot.channel_id)
        if existing:
            raise ValueError(f"Already watching {existing.display_title}.")

    channel_pk = uuid.uuid4().hex
    now = _utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO watch_channels (
                id, url, channel_id, title, enabled, language, transcript_source,
                pad_start, pad_end, reencode, min_duration, created_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel_pk,
                snapshot.url,
                snapshot.channel_id or None,
                snapshot.title,
                language,
                transcript_source,
                pad_start,
                pad_end,
                int(reencode),
                min_duration,
                now,
            ),
        )
        for video in snapshot.videos:
            if video.is_pending_live:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO watch_videos (
                    channel_pk, video_id, title, url, duration, seen_at, job_id, skip_reason
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'already_published')
                """,
                (
                    channel_pk,
                    video.id,
                    video.title,
                    video.url,
                    video.duration,
                    now,
                ),
            )
        conn.execute(
            "UPDATE watch_channels SET last_checked_at = ?, last_error = NULL WHERE id = ?",
            (now, channel_pk),
        )

    channel = get_channel(channel_pk)
    if channel is None:
        raise RuntimeError("Failed to save channel")
    return channel


def set_enabled(channel_pk: str, enabled: bool) -> WatchChannel:
    with connect() as conn:
        conn.execute(
            "UPDATE watch_channels SET enabled = ? WHERE id = ?",
            (int(enabled), channel_pk),
        )
    channel = get_channel(channel_pk)
    if channel is None:
        raise ValueError("Channel not found")
    return channel


def delete_channel(channel_pk: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM watch_videos WHERE channel_pk = ?", (channel_pk,))
        conn.execute("DELETE FROM watch_channels WHERE id = ?", (channel_pk,))


def poll_all_channels(*, only_enabled: bool = True) -> PollResult:
    if not _poll_lock.acquire(blocking=False):
        return PollResult(busy=True, message="A check is already running.")
    try:
        apply_settings()
        result = PollResult()
        channels = list_channels()
        if only_enabled:
            channels = [channel for channel in channels if channel.enabled]
        for channel in channels:
            result.checked += 1
            try:
                queued = _poll_channel(channel)
                result.queued += queued
            except Exception as exc:
                _mark_error(channel.id, str(exc))
                result.errors.append(f"{channel.display_title}: {exc}")
        if result.queued:
            result.message = (
                f"Queued {result.queued} new video"
                f"{'s' if result.queued != 1 else ''}."
            )
        elif result.checked:
            result.message = "No new videos."
        else:
            result.message = "No channels are being watched."
        return result
    finally:
        _poll_lock.release()


def poll_one_channel(channel_pk: str) -> PollResult:
    channel = get_channel(channel_pk)
    if channel is None:
        return PollResult(message="Channel not found.", errors=["Channel not found."])
    if not _poll_lock.acquire(blocking=False):
        return PollResult(busy=True, message="A check is already running.")
    try:
        apply_settings()
        try:
            queued = _poll_channel(channel)
        except Exception as exc:
            _mark_error(channel.id, str(exc))
            return PollResult(
                checked=1,
                errors=[str(exc)],
                message=str(exc),
            )
        message = (
            f"Queued {queued} new video{'s' if queued != 1 else ''}."
            if queued
            else f"No new videos on {channel.display_title}."
        )
        return PollResult(checked=1, queued=queued, message=message)
    finally:
        _poll_lock.release()


def queue_latest(channel_pk: str) -> PollResult:
    channel = get_channel(channel_pk)
    if channel is None:
        return PollResult(message="Channel not found.", errors=["Channel not found."])
    apply_settings()
    try:
        snapshot = _snapshot_for(channel)
    except Exception as exc:
        _mark_error(channel.id, str(exc))
        return PollResult(checked=1, errors=[str(exc)], message=str(exc))

    _touch_ok(channel.id)
    latest = next((video for video in snapshot.videos if not video.is_pending_live), None)
    if latest is None:
        return PollResult(
            checked=1,
            message="No published video to queue yet (live or upcoming only).",
        )
    job_id = _queue_video(channel, latest, force=True)
    if job_id is None:
        return PollResult(
            checked=1,
            message=f"Latest video is already queued: {latest.title}",
        )
    return PollResult(
        checked=1,
        queued=1,
        message=f"Queued “{latest.title}”.",
    )


def start_monitor() -> None:
    global _monitor_started
    with _monitor_lock:
        if _monitor_started:
            return
        _monitor_started = True
    threading.Thread(target=_monitor_loop, name="channel-watch", daemon=True).start()


def _monitor_loop() -> None:
    init_watch_db()
    time.sleep(8)
    while True:
        try:
            if enabled_count():
                result = poll_all_channels()
                if result.queued:
                    print(f"Watch: queued {result.queued} new video(s)")
                for error in result.errors or []:
                    print(f"Watch: {error}")
        except Exception as exc:
            print(f"Watch: poll failed: {exc}")
            traceback.print_exc()
        time.sleep(max(60.0, CHANNEL_POLL_SECONDS))


def _find_by_channel_id(channel_id: str) -> WatchChannel | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM watch_channels WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    return WatchChannel.from_row(row) if row else None


def _snapshot_for(channel: WatchChannel) -> ChannelSnapshot:
    target = ""
    if channel.channel_id and channel.channel_id.startswith("UC"):
        target = f"https://www.youtube.com/channel/{channel.channel_id}/videos"
    else:
        target = channel.url
    return probe_channel(target, recent=CHANNEL_RECENT_VIDEOS)


def _poll_channel(channel: WatchChannel) -> int:
    snapshot = _snapshot_for(channel)
    queued = 0
    if snapshot.title and snapshot.title != channel.title:
        with connect() as conn:
            conn.execute(
                "UPDATE watch_channels SET title = ?, channel_id = COALESCE(?, channel_id) WHERE id = ?",
                (snapshot.title, snapshot.channel_id or None, channel.id),
            )
    for video in snapshot.videos:
        if video.is_pending_live:
            continue
        if _already_seen(channel.id, video.id):
            continue
        skip = _skip_reason(channel, video)
        if skip:
            _mark_seen(channel, video, skip_reason=skip)
            continue
        if _queue_video(channel, video, force=False):
            queued += 1
            print(f"Watch: queued {video.url} from {channel.display_title}")
    _touch_ok(channel.id)
    return queued


def _skip_reason(channel: WatchChannel, video: ChannelVideo) -> str | None:
    if video.duration is not None and video.duration < channel.min_duration:
        return "short"
    return None


def _already_seen(channel_pk: str, video_id: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM watch_videos WHERE channel_pk = ? AND video_id = ?",
            (channel_pk, video_id),
        ).fetchone()
    return row is not None


def _mark_seen(channel: WatchChannel, video: ChannelVideo, *, skip_reason: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO watch_videos (
                channel_pk, video_id, title, url, duration, seen_at, job_id, skip_reason
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                channel.id,
                video.id,
                video.title,
                video.url,
                video.duration,
                _utc_now(),
                skip_reason,
            ),
        )


def _queue_video(channel: WatchChannel, video: ChannelVideo, *, force: bool) -> str | None:
    job_id = uuid.uuid4().hex
    now = _utc_now()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT job_id FROM watch_videos
            WHERE channel_pk = ? AND video_id = ?
            """,
            (channel.id, video.id),
        ).fetchone()
        if existing is not None:
            if existing["job_id"] or not force:
                return None
            conn.execute(
                """
                INSERT INTO jobs (
                    id, status, source_type, source_url, source_path, filename,
                    language, transcript_source, pad_start, pad_end,
                    reencode, title, created_at
                ) VALUES (?, 'queued', 'url', ?, NULL, '', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    video.url,
                    channel.language,
                    channel.transcript_source,
                    channel.pad_start,
                    channel.pad_end,
                    int(channel.reencode),
                    video.title,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE watch_videos
                SET job_id = ?, skip_reason = NULL, title = ?, url = ?, duration = ?
                WHERE channel_pk = ? AND video_id = ?
                """,
                (job_id, video.title, video.url, video.duration, channel.id, video.id),
            )
            return job_id

        try:
            conn.execute(
                """
                INSERT INTO watch_videos (
                    channel_pk, video_id, title, url, duration, seen_at, job_id, skip_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    channel.id,
                    video.id,
                    video.title,
                    video.url,
                    video.duration,
                    now,
                    job_id,
                ),
            )
        except sqlite3.IntegrityError:
            return None
        conn.execute(
            """
            INSERT INTO jobs (
                id, status, source_type, source_url, source_path, filename,
                language, transcript_source, pad_start, pad_end,
                reencode, title, created_at
            ) VALUES (?, 'queued', 'url', ?, NULL, '', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                video.url,
                channel.language,
                channel.transcript_source,
                channel.pad_start,
                channel.pad_end,
                int(channel.reencode),
                video.title,
                now,
            ),
        )
    return job_id


def _touch_ok(channel_pk: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE watch_channels SET last_checked_at = ?, last_error = NULL WHERE id = ?",
            (_utc_now(), channel_pk),
        )


def _mark_error(channel_pk: str, error: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE watch_channels
            SET last_checked_at = ?, last_error = ?
            WHERE id = ?
            """,
            (_utc_now(), error[:2000], channel_pk),
        )


def page_context(
    *,
    error: str | None = None,
    notice: str | None = None,
) -> dict[str, Any]:
    return {
        "channels": list_channels(),
        "discoveries": list_discoveries(),
        "poll_minutes": max(1, int(CHANNEL_POLL_SECONDS // 60)),
        "error": error,
        "notice": notice,
    }
