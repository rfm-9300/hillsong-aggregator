from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from sermon_cut.detect import SermonWindow, detect_from_transcript
from sermon_cut.media import cut_video, extract_audio, probe_duration
from sermon_cut.transcript import Transcript
from sermon_cut.transcribe import transcribe_audio
from sermon_cut.youtube import (
    RemoteVideo,
    download_video,
    fetch_captions,
    pick_caption_track,
    probe_video,
)

PROVIDERS = ("openrouter", "openai", "groq", "gemini", "anthropic")
TRANSCRIPT_SOURCES = ("auto", "captions", "whisper")


@dataclass
class RunConfig:
    video: Path | None = None
    url: str | None = None
    output: Path | None = None
    transcribe: str = "auto"
    llm: str = "auto"
    model: str | None = None
    language: str | None = None
    transcript_source: str = "auto"
    pad_start: float = 2.0
    pad_end: float = 5.0
    reencode: bool = False
    dry_run: bool = False
    work_dir: Path = Path(".work")
    keep_work: bool = False


@dataclass
class RunResult:
    window: SermonWindow
    output: Path | None
    transcript: Transcript | None
    transcript_source: str = "whisper"
    source_title: str | None = None


def run(config: RunConfig) -> RunResult:
    load_dotenv()
    if config.transcript_source not in TRANSCRIPT_SOURCES:
        raise ValueError(f"Unknown transcript source: {config.transcript_source}")
    if bool(config.video) == bool(config.url):
        raise ValueError("Provide either a video file or a URL, not both")

    llm = _resolve_provider(config.llm, for_whisper=False)
    if config.model:
        _apply_model(llm, config.model)

    work_dir = config.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    video: Path | None = None
    if config.video:
        video = config.video.expanduser().resolve()
        if not video.exists():
            raise FileNotFoundError(f"Video not found: {video}")

    remote: RemoteVideo | None = None
    transcript: Transcript | None = None
    transcript_source = "whisper"
    duration: float | None = None

    if config.url:
        print(f"Reading {config.url}…")
        remote = probe_video(config.url)
        duration = remote.duration
        print(f"Source: {remote.title or remote.url}")
        if config.transcript_source in {"auto", "captions"}:
            transcript = _captions_transcript(remote, work_dir, config.language)
            if transcript is not None:
                transcript_source = "captions"
            elif config.transcript_source == "captions":
                raise RuntimeError(
                    "No usable captions for that video. Re-run with transcript source 'whisper'."
                )
        # Captions plus a dry run means we never have to pull the video down.
        if transcript is None or not config.dry_run:
            print("Downloading video…")
            video = download_video(remote, work_dir / "download")
            print(f"Downloaded {video.name}")

    if video is not None:
        duration = probe_duration(video)
    if duration is None:
        raise RuntimeError("Could not determine the video duration")
    print(f"Video duration: {_hms(duration)}")

    if transcript is not None:
        _write_transcript(work_dir, transcript)
        print(f"Captions: {len(transcript.segments)} segments, lang={transcript.language}")
        print(f"Detecting sermon window with {llm}…")
        window = detect_from_transcript(transcript, llm)
    else:
        if video is None:
            raise RuntimeError("No local video available to analyse")
        print(f"Extracting audio from {video.name}…")
        audio = extract_audio(video, work_dir / "audio.mp3")
        provider = _resolve_provider(config.transcribe, for_whisper=True)
        print(f"Transcribing with {provider}…")
        transcript = transcribe_audio(audio, provider, config.language, work_dir)
        _write_transcript(work_dir, transcript)
        print(f"Transcript: {len(transcript.segments)} segments, lang={transcript.language}")
        print(f"Detecting sermon window with {llm}…")
        window = detect_from_transcript(transcript, llm)

    window = window.clamped(duration, config.pad_start, config.pad_end)
    print(json.dumps(window.as_dict(), ensure_ascii=False, indent=2))

    output: Path | None = None
    if not config.dry_run:
        if video is None:
            raise RuntimeError("No local video available to cut")
        if not window.sermon_found:
            print("Warning: model was not confident a sermon was found; cutting the reported window anyway.")
        print(f"Cutting {_hms(window.start_seconds)} → {_hms(window.end_seconds)}…")
        dest = config.output.expanduser().resolve() if config.output else _default_output(video, remote)
        output = cut_video(
            video,
            dest,
            window.start_seconds,
            window.end_seconds,
            reencode=config.reencode,
        )
        print(f"Wrote {output}")

    if not config.keep_work:
        _cleanup(work_dir)

    return RunResult(
        window=window,
        output=output,
        transcript=transcript,
        transcript_source=transcript_source,
        source_title=(remote.title or None) if remote else None,
    )


def _captions_transcript(
    remote: RemoteVideo, work_dir: Path, language: str | None
) -> Transcript | None:
    track = pick_caption_track(remote, language)
    if track is None:
        print("No captions published for that video; falling back to Whisper.")
        return None
    print(f"Found {track.label} captions ({track.language}); skipping Whisper.")
    transcript = fetch_captions(remote, work_dir / "captions", track)
    if transcript is None:
        print("Captions could not be read; falling back to Whisper.")
    return transcript


def _write_transcript(work_dir: Path, transcript: Transcript) -> None:
    (work_dir / "transcript.json").write_text(
        json.dumps(
            {
                "language": transcript.language,
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in transcript.segments
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _default_output(video: Path, remote: RemoteVideo | None) -> Path:
    if remote is not None:
        stem = _slug(remote.title) or remote.id or "sermon"
        return Path.cwd() / f"{stem}_sermon.mp4"
    return video.with_name(f"{video.stem}_sermon.mp4")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\- ]+", "", value).strip()
    return re.sub(r"[\s_]+", "_", cleaned)[:80]


def _apply_model(llm: str, model: str) -> None:
    env_key = {
        "openrouter": "OPENROUTER_MODEL",
        "openai": "OPENAI_MODEL",
        "groq": "GROQ_MODEL",
        "gemini": "GEMINI_MODEL",
        "anthropic": "ANTHROPIC_MODEL",
    }.get(llm)
    if env_key:
        os.environ[env_key] = model


def _resolve_provider(name: str, for_whisper: bool) -> str:
    if name != "auto":
        if name not in PROVIDERS:
            raise ValueError(f"Unknown provider: {name}")
        if for_whisper and name == "anthropic":
            raise ValueError("Anthropic cannot transcribe audio. Use openrouter, openai, groq, or gemini.")
        return name

    if for_whisper:
        if os.environ.get("OPENROUTER_API_KEY"):
            return "openrouter"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("GROQ_API_KEY"):
            return "groq"
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            return "gemini"
        raise RuntimeError(
            "No transcription key found. Set OPENROUTER_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY."
        )

    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    raise RuntimeError("No LLM API key found. Set OPENROUTER_API_KEY or another provider key.")


def _cleanup(work_dir: Path) -> None:
    import shutil

    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)


def _hms(seconds: float) -> str:
    from sermon_cut.transcript import fmt_ts

    return fmt_ts(seconds)
