from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sermon_cut.captions import parse_vtt
from sermon_cut.transcript import Transcript

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
SKIP_SUFFIXES = {".part", ".ytdl", ".vtt", ".srt", ".json", ".jpg", ".webp", ".png"}
CHANNEL_PATH_RE = re.compile(
    r"^/(?:@[\w.-]+|channel/UC[\w-]+|c/[\w.-]+|user/[\w.-]+)(?:/.*)?$",
    re.IGNORECASE,
)
CHANNEL_ROOT_RE = re.compile(
    r"^(/@[\w.-]+|/channel/UC[\w-]+|/c/[\w.-]+|/user/[\w.-]+)",
    re.IGNORECASE,
)
VIDEO_PATH_RE = re.compile(
    r"youtu\.be/|youtube\.com/(?:watch|shorts|embed|live)\b",
    re.IGNORECASE,
)
CHANNEL_TAB_RE = re.compile(
    r"^/(videos|shorts|streams|live|releases|playlists)$",
    re.IGNORECASE,
)


class DownloadError(RuntimeError):
    pass


def is_url(value: object) -> bool:
    return bool(URL_RE.match(str(value).strip()))


def is_channel_url(value: object) -> bool:
    raw = str(value).strip()
    if not URL_RE.match(raw) or VIDEO_PATH_RE.search(raw):
        return False
    host = (urlparse(raw).hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return False
    return bool(CHANNEL_PATH_RE.match(urlparse(raw).path or ""))


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def normalize_channel_url(url: str) -> str:
    """Point a channel link at the uploads tab unless a tab is already specified."""
    parsed = urlparse(url.strip())
    path = (parsed.path or "").rstrip("/")
    root_match = CHANNEL_ROOT_RE.match(path)
    if not root_match:
        return url.strip()
    root = root_match.group(1)
    remainder = path[len(root) :]
    if CHANNEL_TAB_RE.match(remainder):
        normalized = root + remainder
    else:
        normalized = f"{root}/videos"
    return urlunparse(parsed._replace(path=normalized, query="", fragment=""))


@dataclass
class CaptionTrack:
    language: str
    auto: bool

    @property
    def label(self) -> str:
        return "auto-generated" if self.auto else "published"


@dataclass
class RemoteVideo:
    url: str
    id: str
    title: str
    duration: float | None
    language: str | None
    manual_langs: list[str] = field(default_factory=list)
    auto_langs: list[str] = field(default_factory=list)

    @property
    def has_captions(self) -> bool:
        return bool(self.manual_langs or self.auto_langs)


@dataclass
class ChannelVideo:
    id: str
    title: str
    url: str
    duration: float | None
    live_status: str | None

    @property
    def is_pending_live(self) -> bool:
        return (self.live_status or "") in {"is_live", "is_upcoming", "post_live"}


@dataclass
class ChannelSnapshot:
    url: str
    channel_id: str
    title: str
    videos: list[ChannelVideo] = field(default_factory=list)


def probe_channel(url: str, *, recent: int = 20) -> ChannelSnapshot:
    """Resolve a channel URL and list the newest uploads without downloading."""
    if not is_channel_url(url):
        raise DownloadError(
            "Paste a channel URL such as https://www.youtube.com/@handle, not a video link."
        )
    target = normalize_channel_url(url)
    raw = _capture(
        [
            "--flat-playlist",
            "--dump-single-json",
            "--playlist-end",
            str(max(1, recent)),
            "--ignore-no-formats-error",
            target,
        ],
        allow_playlist=True,
        timeout=90,
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DownloadError(f"yt-dlp returned unreadable channel metadata: {exc}") from exc

    entries = [entry for entry in (data.get("entries") or []) if isinstance(entry, dict)]
    if data.get("_type") != "playlist" and not entries:
        raise DownloadError(
            "That looks like a video, not a channel. Paste https://www.youtube.com/@handle"
        )

    channel_id = ""
    for key in ("channel_id", "uploader_id", "id"):
        value = str(data.get(key) or "").strip()
        if value.startswith("UC"):
            channel_id = value
            break
        if value and not channel_id:
            channel_id = value
    title = str(
        data.get("channel") or data.get("uploader") or data.get("title") or ""
    ).strip()
    videos: list[ChannelVideo] = []
    seen: set[str] = set()
    for entry in entries:
        if entry.get("_type") == "playlist":
            continue
        video_id = str(entry.get("id") or "").strip()
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        duration = entry.get("duration")
        videos.append(
            ChannelVideo(
                id=video_id,
                title=str(entry.get("title") or "").strip() or video_id,
                url=watch_url(video_id),
                duration=float(duration) if duration else None,
                live_status=(str(entry["live_status"]) if entry.get("live_status") else None),
            )
        )

    if not channel_id and not title:
        raise DownloadError("Could not read that YouTube channel.")
    return ChannelSnapshot(
        url=target,
        channel_id=channel_id,
        title=title or channel_id or target,
        videos=videos,
    )


def probe_video(url: str) -> RemoteVideo:
    """Read title, duration, and available caption tracks without downloading."""
    raw = _capture(["--dump-single-json", "--skip-download", url])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DownloadError(f"yt-dlp returned unreadable metadata: {exc}") from exc

    if data.get("_type") == "playlist":
        entries = [entry for entry in (data.get("entries") or []) if entry]
        if not entries:
            raise DownloadError("That URL has no playable video.")
        data = entries[0]
    if data.get("is_live"):
        raise DownloadError("That video is still live. Wait until the stream ends.")

    duration = data.get("duration")
    return RemoteVideo(
        url=data.get("webpage_url") or url,
        id=str(data.get("id") or ""),
        title=str(data.get("title") or "").strip(),
        duration=float(duration) if duration else None,
        language=(data.get("language") or None),
        # Keep yt-dlp's order: it lists the spoken language first, translations after.
        manual_langs=list((data.get("subtitles") or {}).keys()),
        auto_langs=list((data.get("automatic_captions") or {}).keys()),
    )


def pick_caption_track(remote: RemoteVideo, language: str | None) -> CaptionTrack | None:
    """Published captions beat auto-generated ones; the original language beats translations."""
    wanted = _base_lang(language) if language else None

    if wanted:
        match = _first_match(remote.manual_langs, wanted)
        if match:
            return CaptionTrack(match, auto=False)
        match = _first_match(remote.auto_langs, wanted)
        if match:
            return CaptionTrack(match, auto=True)
        return None

    source_lang = _base_lang(remote.language) if remote.language else None
    if source_lang:
        match = _first_match(remote.manual_langs, source_lang)
        if match:
            return CaptionTrack(match, auto=False)
    if remote.manual_langs:
        return CaptionTrack(remote.manual_langs[0], auto=False)

    original = next((code for code in remote.auto_langs if code.endswith("-orig")), None)
    if original:
        return CaptionTrack(original, auto=True)
    if source_lang:
        match = _first_match(remote.auto_langs, source_lang)
        if match:
            return CaptionTrack(match, auto=True)
    if remote.auto_langs:
        return CaptionTrack(remote.auto_langs[0], auto=True)
    return None


def fetch_captions(remote: RemoteVideo, dest_dir: Path, track: CaptionTrack) -> Transcript | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    _stream(
        [
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            track.language,
            "--sub-format",
            "vtt",
            "-o",
            str(dest_dir / "captions.%(ext)s"),
            remote.url,
        ]
    )
    files = sorted(dest_dir.glob("*.vtt"))
    if not files:
        return None
    transcript = parse_vtt(
        files[0].read_text(encoding="utf-8", errors="replace"),
        language=_base_lang(track.language),
    )
    return transcript if transcript.segments else None


def download_video(remote: RemoteVideo, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    fmt = os.environ.get(
        "YTDLP_FORMAT",
        "bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/"
        "bv*[vcodec^=avc1][height<=1080]+ba/"
        "b[ext=mp4][height<=1080]/b",
    )
    _stream(
        [
            "-f",
            fmt,
            "--merge-output-format",
            "mp4",
            "-o",
            str(dest_dir / "source.%(ext)s"),
            remote.url,
        ]
    )
    candidates = [
        path
        for path in dest_dir.glob("source.*")
        if path.is_file() and path.suffix.lower() not in SKIP_SUFFIXES
    ]
    if not candidates:
        raise DownloadError("yt-dlp finished but no video file was written.")
    return max(candidates, key=lambda path: path.stat().st_size)


def _base_lang(code: str) -> str:
    return code.strip().lower().removesuffix("-orig").split("-")[0]


def _first_match(codes: list[str], wanted: str) -> str | None:
    for code in codes:
        if code.strip().lower() == wanted:
            return code
    for code in codes:
        if _base_lang(code) == wanted:
            return code
    return None


def _ytdlp_command(*, allow_playlist: bool = False) -> list[str]:
    exe = shutil.which("yt-dlp")
    if exe:
        base = [exe]
    elif importlib.util.find_spec("yt_dlp") is not None:
        base = [sys.executable, "-m", "yt_dlp"]
    else:
        raise DownloadError("yt-dlp is not installed. Install it with: pip install yt-dlp")

    base += ["--no-color", "--newline"]
    if allow_playlist:
        base.append("--yes-playlist")
    else:
        base.append("--no-playlist")
    cookies = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if cookies:
        base += ["--cookies", cookies]
    browser = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if browser:
        base += ["--cookies-from-browser", browser]
    extra = os.environ.get("YTDLP_EXTRA_ARGS", "").strip()
    if extra:
        base += shlex.split(extra)
    return base


def _capture(
    args: list[str],
    *,
    allow_playlist: bool = False,
    timeout: float | None = None,
) -> str:
    try:
        proc = subprocess.run(
            _ytdlp_command(allow_playlist=allow_playlist) + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise DownloadError("yt-dlp timed out while reading the channel.") from exc
    if proc.returncode != 0:
        raise DownloadError(_tidy_error(proc.stderr or proc.stdout))
    return proc.stdout


def _stream(args: list[str], progress_every: float = 3.0) -> None:
    """Run yt-dlp, forwarding output through print() so the job log captures it."""
    proc = subprocess.Popen(
        _ytdlp_command() + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    tail: list[str] = []
    last_progress = 0.0
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        if not line:
            continue
        tail.append(line)
        del tail[:-20]
        if line.startswith("[download]") and "%" in line:
            now = time.monotonic()
            if now - last_progress < progress_every:
                continue
            last_progress = now
        print(line)
    if proc.wait() != 0:
        raise DownloadError(_tidy_error("\n".join(tail)))


def _tidy_error(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    errors = [line for line in lines if line.upper().startswith("ERROR")]
    detail = "\n".join(errors[-3:] or lines[-5:])
    return f"yt-dlp failed: {detail}" if detail else "yt-dlp failed"
