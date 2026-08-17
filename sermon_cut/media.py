from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


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


def probe_video(path: Path) -> dict[str, Any]:
    """Return size, fps, duration, codecs, and whether audio exists."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FFmpegError("ffprobe is not installed (it ships with ffmpeg).")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration",
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
    width = height = 0
    fps = 30.0
    has_audio = False
    vcodec = ""
    acodec = ""
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video" and not width:
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            vcodec = str(stream.get("codec_name") or "")
            rate = str(stream.get("r_frame_rate") or "30/1")
            if "/" in rate:
                num, den = rate.split("/", 1)
                try:
                    fps = float(num) / float(den) if float(den) else 30.0
                except ValueError:
                    fps = 30.0
            else:
                try:
                    fps = float(rate)
                except ValueError:
                    fps = 30.0
        elif stream.get("codec_type") == "audio" and not acodec:
            has_audio = True
            acodec = str(stream.get("codec_name") or "")
    duration = float((data.get("format") or {}).get("duration") or 0.0)
    if width <= 0 or height <= 0:
        raise FFmpegError(f"Could not read video size from {path.name}")
    return {
        "width": width,
        "height": height,
        "fps": max(1.0, min(fps, 60.0)),
        "duration": duration,
        "has_audio": has_audio,
        "vcodec": vcodec,
        "acodec": acodec,
    }


def _even(value: int) -> int:
    return value - (value % 2)


def _is_stream_copy_friendly(info: dict[str, Any]) -> bool:
    """H.264 + AAC (or silent) can be concat-demuxed without re-encoding."""
    vcodec = (info.get("vcodec") or "").lower()
    acodec = (info.get("acodec") or "").lower()
    video_ok = vcodec in {"h264", "avc1", "avc"}
    audio_ok = (not info.get("has_audio")) or acodec in {"aac", "mp4a"}
    return video_ok and audio_ok


def _transcode_clip(
    src: Path,
    dest: Path,
    *,
    width: int,
    height: int,
    fps: float,
) -> Path:
    """Re-encode a clip to H.264/AAC matching the target frame size."""
    info = probe_video(src)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:.3f},format=yuv420p"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    if info["has_audio"]:
        run_ffmpeg(
            [
                "-i",
                str(src),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-b:a",
                "192k",
                str(dest),
            ]
        )
    else:
        duration = max(float(info["duration"] or 0.1), 0.1)
        run_ffmpeg(
            [
                "-i",
                str(src),
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=stereo:sample_rate=48000",
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-t",
                f"{duration:.3f}",
                str(dest),
            ]
        )
    return dest


def _concat_copy(parts: list[Path], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_path = dest.parent / f".{dest.stem}.concat.txt"
    lines: list[str] = []
    for path in parts:
        escaped = str(path.resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(dest),
            ]
        )
    finally:
        list_path.unlink(missing_ok=True)
    return dest


def stitch_clips(parts: list[Path], dest: Path) -> Path:
    """Join clips end-to-end.

    Fast path: re-encode only short mismatched clips to H.264/AAC, then concat with
    stream copy. Slow path (fallback): filter-complex re-encode of everything.
    """
    if not parts:
        raise FFmpegError("No clips to stitch")
    resolved = [p.expanduser().resolve() for p in parts]
    for path in resolved:
        if not path.is_file():
            raise FFmpegError(f"Missing clip: {path}")
    if len(resolved) == 1:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if resolved[0] != dest.resolve():
            shutil.copy2(resolved[0], dest)
        return dest

    # Longest clip is the sermon — keep its resolution as the target.
    infos = [probe_video(path) for path in resolved]
    sermon_index = max(range(len(resolved)), key=lambda i: infos[i]["duration"])
    target = infos[sermon_index]
    width = _even(int(target["width"]))
    height = _even(int(target["height"]))
    fps = round(float(target["fps"]), 3) or 30.0

    work = dest.parent / f".stitch_{dest.stem}"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    try:
        normalized: list[Path] = []
        for index, path in enumerate(resolved):
            info = infos[index]
            if index == sermon_index and _is_stream_copy_friendly(info):
                print(f"Keeping sermon stream as-is ({path.name}, {info['vcodec']}+{info['acodec'] or 'silent'})")
                normalized.append(path)
                continue
            label = "sermon" if index == sermon_index else f"clip {index + 1}/{len(resolved)}"
            if index == sermon_index:
                print(
                    f"Re-encoding {label} to H.264 for packaging "
                    f"(source is {info['vcodec'] or 'unknown'}; this may take a while)…"
                )
            else:
                print(f"Normalizing {label} ({path.name})…")
            out = work / f"part_{index:02d}.mp4"
            _transcode_clip(path, out, width=width, height=height, fps=fps)
            normalized.append(out)

        print("Joining intro/sermon/ending…")
        return _concat_copy(normalized, dest)
    except FFmpegError as exc:
        print(f"Fast packaging failed ({exc}); falling back to full re-encode…")
        return _stitch_clips_filter(resolved, dest, width=width, height=height, fps=fps)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _stitch_clips_filter(
    resolved: list[Path],
    dest: Path,
    *,
    width: int,
    height: int,
    fps: float,
) -> Path:
    """Slow fallback: decode everything and re-encode once."""
    inputs: list[str] = []
    filters: list[str] = []
    concat_refs: list[str] = []
    for index, path in enumerate(resolved):
        info = probe_video(path)
        inputs.extend(["-i", str(path)])
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},"
            f"format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
        )
        if info["has_audio"]:
            filters.append(
                f"[{index}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                f"aresample=async=1,asetpts=PTS-STARTPTS[a{index}]"
            )
        else:
            duration = max(info["duration"], 0.1)
            filters.append(
                f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=0:{duration:.3f},"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
        concat_refs.append(f"[v{index}][a{index}]")

    n = len(resolved)
    filters.append(f"{''.join(concat_refs)}concat=n={n}:v=1:a=1[v][a]")
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(dest),
        ]
    )
    return dest


def package_sermon(
    sermon: Path,
    dest: Path,
    *,
    intro: Path | None = None,
    outro: Path | None = None,
) -> Path:
    """Build intro + sermon + ending. Copies sermon through when no bookends."""
    parts: list[Path] = []
    if intro is not None:
        parts.append(intro)
    parts.append(sermon)
    if outro is not None:
        parts.append(outro)
    if len(parts) == 1:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if sermon.resolve() != dest.resolve():
            shutil.copy2(sermon, dest)
        return dest
    return stitch_clips(parts, dest)


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
