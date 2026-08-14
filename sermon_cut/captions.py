from __future__ import annotations

import html
import re

from sermon_cut.transcript import Segment, Transcript, parse_ts

TIMING = re.compile(
    r"(?P<start>(?:\d+:)?\d{1,3}:\d{2}[.,]\d{1,3})\s*-->\s*(?P<end>(?:\d+:)?\d{1,3}:\d{2}[.,]\d{1,3})"
)
TAG = re.compile(r"<[^>]*>")


def parse_vtt(text: str, language: str | None = None) -> Transcript:
    """Parse WebVTT captions into a Transcript.

    YouTube auto-generated captions repeat the previous cue as a rolling window,
    so identical lines are dropped to keep the LLM prompt small.
    """
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[tuple[float, float, list[str]]] = []

    index = 0
    while index < len(lines):
        match = TIMING.search(lines[index])
        if not match:
            index += 1
            continue
        try:
            start = parse_ts(match.group("start"))
            end = parse_ts(match.group("end"))
        except ValueError:
            index += 1
            continue
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip():
            if TIMING.search(lines[index]):
                break
            cleaned = _clean(lines[index])
            if cleaned:
                body.append(cleaned)
            index += 1
        if body and end > start:
            cues.append((start, end, body))

    return Transcript(language=language, segments=_dedupe(cues))


def _clean(line: str) -> str:
    return " ".join(html.unescape(TAG.sub("", line)).split())


def _dedupe(cues: list[tuple[float, float, list[str]]]) -> list[Segment]:
    segments: list[Segment] = []
    previous: list[str] = []
    for start, end, body in cues:
        fresh = [line for line in body if line not in previous]
        previous = body
        text = " ".join(fresh).strip()
        if not text:
            continue
        if segments:
            last = segments[-1]
            if text == last.text:
                last.end = max(last.end, end)
                continue
            if text.startswith(last.text + " "):
                text = text[len(last.text) + 1 :].strip()
                if not text:
                    last.end = max(last.end, end)
                    continue
        segments.append(Segment(start, end, text))
    return segments
