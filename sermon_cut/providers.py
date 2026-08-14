from __future__ import annotations

import os

from openai import OpenAI

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"
DEFAULT_OPENROUTER_WHISPER = "openai/whisper-large-v3"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def openrouter_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {require_env('OPENROUTER_API_KEY')}",
        "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://localhost"),
        "X-Title": os.environ.get("OPENROUTER_TITLE", "sermon-cut"),
    }


def openrouter_client() -> OpenAI:
    return OpenAI(
        api_key=require_env("OPENROUTER_API_KEY"),
        base_url=OPENROUTER_BASE,
        default_headers={
            "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://localhost"),
            "X-Title": os.environ.get("OPENROUTER_TITLE", "sermon-cut"),
        },
    )


def openai_compat_client(provider: str) -> tuple[OpenAI, str]:
    if provider == "openrouter":
        model = os.environ.get("OPENROUTER_WHISPER_MODEL", DEFAULT_OPENROUTER_WHISPER)
        return openrouter_client(), model
    if provider == "groq":
        client = OpenAI(
            api_key=require_env("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
        return client, os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3")
    client = OpenAI(api_key=require_env("OPENAI_API_KEY"))
    return client, os.environ.get("OPENAI_WHISPER_MODEL", "whisper-1")
