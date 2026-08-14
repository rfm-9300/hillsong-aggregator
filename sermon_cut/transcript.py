from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    start: float
    end: float
    text: str

    def shifted(self, offset: float) -> "Segment":
        return Segment(self.start + offset, self.end + offset, self.text)


@dataclass
class Transcript:
    language: str | None
    segments: list[Segment] = field(default_factory=list)

    def merged(self, window: float = 25.0) -> list[Segment]:
        """Collapse short Whisper segments into larger blocks for the LLM."""
        if not self.segments:
            return []
        blocks: list[Segment] = []
        cur_start = self.segments[0].start
        cur_end = self.segments[0].end
        parts: list[str] = []
        for seg in self.segments:
            text = seg.text.strip()
            if not text:
                continue
            if parts and (seg.end - cur_start) > window:
                blocks.append(Segment(cur_start, cur_end, " ".join(parts)))
                cur_start = seg.start
                parts = [text]
            else:
                if not parts:
                    cur_start = seg.start
                parts.append(text)
            cur_end = seg.end
        if parts:
            blocks.append(Segment(cur_start, cur_end, " ".join(parts)))
        return blocks

    def as_prompt(self, window: float = 25.0) -> str:
        lines: list[str] = []
        for i, seg in enumerate(self.merged(window)):
            lines.append(
                f"[{i:04d}] {fmt_ts(seg.start)} → {fmt_ts(seg.end)}\n{seg.text.strip()}"
            )
        return "\n\n".join(lines)


def fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_ts(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    value = value.strip()
    if not value:
        raise ValueError("empty timestamp")
    if ":" not in value:
        return float(value)
    parts = value.split(":")
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    raise ValueError(f"Bad timestamp: {value}")
