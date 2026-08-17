from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import ensure_dirs


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    group: str
    kind: str
    placeholder: str = ""
    hint: str = ""


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    blurb: str


GROUPS: tuple[Group, ...] = (
    Group("openrouter", "OpenRouter", "Default path. One key covers the chat model and Whisper."),
    Group("openai", "OpenAI", "Used if you point auto-detect at OpenAI, or OpenRouter is unset."),
    Group("groq", "Groq", "Fast Whisper fallback."),
    Group("gemini", "Gemini", "Direct Google key, if you are not going through OpenRouter."),
    Group("anthropic", "Anthropic", "Chat-only. Cannot transcribe."),
    Group("youtube", "YouTube downloads", "Optional yt-dlp tuning for link jobs."),
    Group("dashboard", "Dashboard login", "Takes effect on the next request. Does not require a rebuild."),
)

FIELDS: tuple[Field, ...] = (
    Field("OPENROUTER_API_KEY", "API key", "openrouter", "secret", "sk-or-…"),
    Field(
        "OPENROUTER_MODEL",
        "Chat model",
        "openrouter",
        "text",
        "google/gemini-2.5-flash",
        "Picks sermon start and end from the transcript.",
    ),
    Field(
        "OPENROUTER_WHISPER_MODEL",
        "Whisper model",
        "openrouter",
        "text",
        "openai/whisper-large-v3",
        "Used only when captions are missing.",
    ),
    Field("OPENAI_API_KEY", "API key", "openai", "secret", "sk-…"),
    Field("OPENAI_MODEL", "Chat model", "openai", "text", "gpt-4o"),
    Field("OPENAI_WHISPER_MODEL", "Whisper model", "openai", "text", "whisper-1"),
    Field("GROQ_API_KEY", "API key", "groq", "secret"),
    Field("GROQ_MODEL", "Chat model", "groq", "text", "llama-3.3-70b-versatile"),
    Field("GROQ_WHISPER_MODEL", "Whisper model", "groq", "text", "whisper-large-v3"),
    Field("GEMINI_API_KEY", "API key", "gemini", "secret"),
    Field("GEMINI_MODEL", "Chat model", "gemini", "text", "gemini-2.5-flash"),
    Field("GEMINI_TRANSCRIBE_MODEL", "Transcribe model", "gemini", "text", "gemini-2.5-flash"),
    Field("ANTHROPIC_API_KEY", "API key", "anthropic", "secret"),
    Field("ANTHROPIC_MODEL", "Chat model", "anthropic", "text", "claude-sonnet-4-20250514"),
    Field(
        "YTDLP_FORMAT",
        "Format",
        "youtube",
        "text",
        "bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/bv*[vcodec^=avc1][height<=1080]+ba/b[ext=mp4][height<=1080]/b",
        "Prefer H.264/AAC up to 1080p so packaging stays fast (AV1 downloads are slow to re-encode).",
    ),
    Field("YTDLP_COOKIES_FILE", "Cookies file", "youtube", "text", "/data/cookies.txt"),
    Field("DASHBOARD_USER", "Username", "dashboard", "text", "admin"),
    Field("DASHBOARD_PASSWORD", "Password", "dashboard", "secret"),
)

FIELD_BY_KEY = {field.key: field for field in FIELDS}

_bootstrap: dict[str, str] | None = None


def reset_runtime_state() -> None:
    """Test helper: recapture bootstrap from the current process env."""
    global _bootstrap
    _bootstrap = None


def settings_path() -> Path:
    from app.config import DATA_DIR

    return DATA_DIR / "settings.json"


def _ensure_bootstrap() -> dict[str, str]:
    global _bootstrap
    if _bootstrap is None:
        _bootstrap = {field.key: os.environ.get(field.key, "") for field in FIELDS}
    return _bootstrap


def read_saved() -> dict[str, str]:
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in data.items():
        if key in FIELD_BY_KEY and isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def write_saved(values: dict[str, str]) -> None:
    ensure_dirs()
    clean = {
        key: value.strip()
        for key, value in values.items()
        if key in FIELD_BY_KEY and value.strip()
    }
    path = settings_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def apply() -> dict[str, str]:
    """Overlay saved settings on top of the process/.env bootstrap. Safe to call often."""
    bootstrap = _ensure_bootstrap()
    saved = read_saved()
    for field in FIELDS:
        value = saved.get(field.key) or bootstrap.get(field.key, "")
        if value:
            os.environ[field.key] = value
        else:
            os.environ.pop(field.key, None)
    return saved


def save_from_form(form: dict[str, str]) -> dict[str, str]:
    previous = read_saved()
    next_vals: dict[str, str] = {}
    for field in FIELDS:
        raw = (form.get(field.key) or "").strip()
        if field.kind == "secret":
            if raw:
                next_vals[field.key] = raw
            elif field.key in previous:
                next_vals[field.key] = previous[field.key]
        elif raw:
            next_vals[field.key] = raw
    write_saved(next_vals)
    apply()
    return next_vals


def effective(key: str) -> str:
    apply()
    return os.environ.get(key, "").strip()


def provider_status() -> list[dict[str, str | bool]]:
    apply()
    checks = (
        ("OpenRouter", bool(os.environ.get("OPENROUTER_API_KEY"))),
        ("OpenAI", bool(os.environ.get("OPENAI_API_KEY"))),
        ("Groq", bool(os.environ.get("GROQ_API_KEY"))),
        ("Gemini", bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))),
        ("Anthropic", bool(os.environ.get("ANTHROPIC_API_KEY"))),
    )
    return [{"name": name, "configured": configured} for name, configured in checks]


def form_groups() -> list[dict]:
    saved = read_saved()
    bootstrap = _ensure_bootstrap()
    grouped: list[dict] = []
    for group in GROUPS:
        rows = []
        for field in FIELDS:
            if field.group != group.id:
                continue
            saved_val = saved.get(field.key, "")
            env_val = bootstrap.get(field.key, "")
            current = saved_val or env_val
            if saved_val:
                source = "saved"
            elif env_val:
                source = "env"
            else:
                source = "unset"
            rows.append(
                {
                    "key": field.key,
                    "label": field.label,
                    "kind": field.kind,
                    "placeholder": field.placeholder,
                    "hint": field.hint,
                    "value": "" if field.kind == "secret" else current,
                    "configured": bool(current),
                    "source": source,
                }
            )
        grouped.append({"id": group.id, "title": group.title, "blurb": group.blurb, "fields": rows})
    return grouped
