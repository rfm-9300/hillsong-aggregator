from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegError(
            "ffmpeg is not installed. On macOS: brew install ffmpeg"
        )
    return path


def run_ffmpeg(args: list[str]) -> None:
    ffmpeg = require_ffmpeg()
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise FFmpegError(detail or f"ffmpeg failed: {' '.join(cmd)}")


def probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FFmpegError("ffprobe is not installed (it ships with ffmpeg).")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip() or "ffprobe failed")
    data = json.loads(proc.stdout)
    return float(data["format"]["duration"])


def extract_audio(video: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            str(dest),
        ]
    )
    return dest


def split_audio(audio: Path, dest_dir: Path, chunk_seconds: int = 600) -> list[tuple[Path, float]]:
    """Split audio into sequential chunks. Returns (path, start_offset_seconds)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(audio)
    chunks: list[tuple[Path, float]] = []
    start = 0.0
    index = 0
    while start < duration:
        out = dest_dir / f"chunk_{index:03d}.mp3"
        run_ffmpeg(
            [
                "-ss",
                f"{start:.3f}",
                "-t",
                str(chunk_seconds),
                "-i",
                str(audio),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "64k",
                str(out),
            ]
        )
        chunks.append((out, start))
        start += chunk_seconds
        index += 1
    return chunks


def cut_video(
    video: Path,
    dest: Path,
    start: float,
    end: float,
    reencode: bool = False,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if end <= start:
        raise FFmpegError(f"Invalid cut window: {start:.2f}s → {end:.2f}s")

    common = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video)]
    if reencode:
        args = [
            *common,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    else:
        args = [
            *common,
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(dest),
        ]
    run_ffmpeg(args)
    return dest


def max_upload_bytes() -> int:
    return 24 * 1024 * 1024


def needs_chunking(audio: Path) -> bool:
    return audio.stat().st_size > max_upload_bytes()
