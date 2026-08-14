from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sermon_cut.pipeline import RunConfig, run
from sermon_cut.youtube import is_url


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract the main sermon from a full church-service video."
    )
    p.add_argument("source", help="Input video (mp4, mkv, mov, …) or a YouTube URL")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output video path (default: <video>_sermon.mp4)",
    )
    p.add_argument(
        "--transcript-source",
        choices=("auto", "captions", "whisper"),
        default="auto",
        help="For URLs: auto reuses published captions when available, then falls back to Whisper.",
    )
    p.add_argument(
        "--transcribe",
        choices=("auto", "openrouter", "openai", "groq", "gemini"),
        default="auto",
        help="Speech-to-text provider used when there are no captions to reuse",
    )
    p.add_argument(
        "--llm",
        choices=("auto", "openrouter", "openai", "groq", "gemini", "anthropic"),
        default="auto",
        help="Model that picks sermon start/end from the transcript",
    )
    p.add_argument(
        "--model",
        help="Chat model id (OpenRouter default: google/gemini-2.5-flash)",
    )
    p.add_argument("--language", help="Whisper/caption language code, e.g. pt or en")
    p.add_argument("--pad-start", type=float, default=2.0, help="Seconds to keep before sermon start")
    p.add_argument("--pad-end", type=float, default=5.0, help="Seconds to keep after sermon end")
    p.add_argument(
        "--reencode",
        action="store_true",
        help="Frame-accurate cut (slower). Default is a fast stream copy.",
    )
    p.add_argument("--dry-run", action="store_true", help="Detect timestamps, do not cut the video")
    p.add_argument("--work-dir", type=Path, default=Path(".work"))
    p.add_argument("--keep-work", action="store_true", help="Keep extracted audio and transcript")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    remote = is_url(args.source)
    video = None if remote else Path(args.source)
    output = args.output
    if output is None and video is not None:
        output = video.with_name(f"{video.stem}_sermon.mp4")
    try:
        run(
            RunConfig(
                video=video,
                url=args.source if remote else None,
                output=output,
                transcribe=args.transcribe,
                llm=args.llm,
                model=args.model,
                language=args.language,
                transcript_source=args.transcript_source,
                pad_start=args.pad_start,
                pad_end=args.pad_end,
                reencode=args.reencode,
                dry_run=args.dry_run,
                work_dir=args.work_dir,
                keep_work=args.keep_work,
            )
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
