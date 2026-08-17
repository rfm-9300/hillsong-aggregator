"""Friendly job progress for the dashboard (non-developer copy)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STATUS_LABELS = {
    "queued": "Waiting",
    "running": "Working",
    "done": "Ready",
    "failed": "Failed",
}

# Ordered pipeline stages shown on the job page.
STEPS: tuple[dict[str, str], ...] = (
    {
        "id": "queue",
        "title": "In line",
        "detail": "Your video is waiting for its turn.",
    },
    {
        "id": "fetch",
        "title": "Getting the video",
        "detail": "Downloading or opening the recording.",
    },
    {
        "id": "listen",
        "title": "Listening for the sermon",
        "detail": "Reading captions or turning speech into text.",
    },
    {
        "id": "find",
        "title": "Finding the sermon",
        "detail": "Figuring out where the sermon starts and ends.",
    },
    {
        "id": "cut",
        "title": "Cutting the clip",
        "detail": "Trimming the video to just the sermon.",
    },
    {
        "id": "package",
        "title": "Adding intro & ending",
        "detail": "Joining your branding clips onto the sermon. Long sermons can take a few minutes.",
    },
    {
        "id": "ready",
        "title": "Ready to watch",
        "detail": "Your sermon clip is ready.",
    },
)

# Latest matching marker wins; order matters within a stage group.
_LOG_MARKERS: tuple[tuple[str, int], ...] = (
    ("downloading video", 1),
    ("reading http", 1),
    ("downloaded ", 1),
    ("video duration:", 1),
    ("no captions published", 2),
    ("falling back to whisper", 2),
    ("skipping whisper", 2),
    ("captions:", 2),
    ("extracting audio", 2),
    ("transcribing with", 2),
    ("transcript:", 2),
    ("detecting sermon", 3),
    ("cutting ", 4),
    ("wrote ", 4),
    ("packaging final", 5),
    ("rebuild requested", 5),
    ("re-encoding sermon", 5),
    ("normalizing ", 5),
    ("joining intro", 5),
    ("wrote packaged", 5),
    ("no intro/ending", 5),
)


@dataclass(frozen=True)
class Progress:
    status: str
    status_label: str
    step_index: int
    percent: int
    headline: str
    detail: str
    steps: list[dict[str, Any]]


def build_progress(*, status: str, log: str = "") -> Progress:
    status_label = STATUS_LABELS.get(status, status)
    last = len(STEPS) - 1

    if status == "failed":
        step_index = _from_log(log, default=1)
        headline = "Something went wrong"
        detail = "See the message above, or open technical details below."
        steps = _steps_view(step_index, failed=True)
        percent = max(8, int(round(100 * step_index / last)))
        return Progress(status, status_label, step_index, percent, headline, detail, steps)

    if status == "done":
        steps = _steps_view(last, failed=False)
        return Progress(
            status,
            status_label,
            last,
            100,
            STEPS[last]["title"],
            "Play the clip below, or download a copy.",
            steps,
        )

    if status == "queued":
        steps = _steps_view(0, failed=False)
        return Progress(
            status,
            status_label,
            0,
            5,
            STEPS[0]["title"],
            STEPS[0]["detail"],
            steps,
        )

    # running
    step_index = max(1, _from_log(log, default=1))
    step_index = min(step_index, last - 1)  # ready only when done
    step = STEPS[step_index]
    percent = max(12, int(round(100 * step_index / last)))
    steps = _steps_view(step_index, failed=False)
    return Progress(
        status,
        status_label,
        step_index,
        percent,
        step["title"],
        step["detail"] + " This page updates automatically.",
        steps,
    )


def format_duration(seconds: Any) -> str:
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "—"
    if total < 0:
        total = 0
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes} min" if secs < 15 else f"{minutes} min {secs}s"
    return f"{secs}s"


def format_confidence(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "—"
    if score > 1:
        score = score / 100.0
    score = max(0.0, min(1.0, score))
    pct = int(round(score * 100))
    if score >= 0.8:
        label = "high"
    elif score >= 0.5:
        label = "medium"
    else:
        label = "low"
    return f"{label} ({pct}%)"


def _from_log(log: str, *, default: int) -> int:
    text = (log or "").lower()
    found = default
    for needle, index in _LOG_MARKERS:
        if needle in text:
            found = max(found, index)
    return found


def _steps_view(current: int, *, failed: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, step in enumerate(STEPS):
        if failed and i == current:
            state = "failed"
        elif i < current:
            state = "done"
        elif i == current:
            state = "current"
        else:
            state = "todo"
        out.append(
            {
                "id": step["id"],
                "title": step["title"],
                "detail": step["detail"],
                "state": state,
            }
        )
    return out
