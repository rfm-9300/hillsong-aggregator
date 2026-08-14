from __future__ import annotations

import os
from pathlib import Path

from sermon_cut.media import needs_chunking, split_audio
from sermon_cut.providers import openai_compat_client
from sermon_cut.transcript import Segment, Transcript


def transcribe_audio(
    audio: Path,
    provider: str,
    language: str | None,
    work_dir: Path,
) -> Transcript:
    if needs_chunking(audio):
        chunks = split_audio(audio, work_dir / "chunks")
        all_segments: list[Segment] = []
        lang: str | None = language
        for path, offset in chunks:
            part = _transcribe_file(path, provider, language)
            if part.language:
                lang = part.language
            all_segments.extend(seg.shifted(offset) for seg in part.segments)
        return Transcript(language=lang, segments=all_segments)
    return _transcribe_file(audio, provider, language)


def _transcribe_file(audio: Path, provider: str, language: str | None) -> Transcript:
    if provider in {"openai", "groq", "openrouter"}:
        return _whisper_openai_compat(audio, provider, language)
    if provider == "gemini":
        return _whisper_gemini(audio, language)
    raise ValueError(f"Unsupported transcribe provider: {provider}")


def _whisper_openai_compat(audio: Path, provider: str, language: str | None) -> Transcript:
    client, model = openai_compat_client(provider)

    handle = audio.open("rb")
    kwargs: dict = {
        "model": model,
        "file": handle,
        "response_format": "verbose_json",
    }
    if provider in {"openai", "openrouter"}:
        kwargs["timestamp_granularities"] = ["segment"]
    if language:
        kwargs["language"] = language

    try:
        try:
            result = client.audio.transcriptions.create(**kwargs)
        except Exception:
            kwargs.pop("timestamp_granularities", None)
            handle.seek(0)
            try:
                result = client.audio.transcriptions.create(**kwargs)
            except Exception:
                if provider != "openrouter":
                    raise
                handle.close()
                return _whisper_openrouter_json(audio, language)
    finally:
        if not handle.closed:
            handle.close()

    raw_segments = result.segments or []
    if not raw_segments and not (getattr(result, "text", "") or "").strip():
        if provider != "openrouter" or model == "openai/whisper-1":
            raise RuntimeError("Transcription returned no text.")

        # Some OpenRouter Whisper models can report success with an empty body.
        kwargs["model"] = "openai/whisper-1"
        handle.seek(0)
        result = client.audio.transcriptions.create(**kwargs)
        raw_segments = result.segments or []

    segments: list[Segment] = []
    for s in raw_segments:
        if isinstance(s, dict):
            segments.append(
                Segment(float(s["start"]), float(s["end"]), str(s.get("text") or ""))
            )
        else:
            segments.append(Segment(float(s.start), float(s.end), s.text or ""))
    if not segments:
        text = getattr(result, "text", "") or ""
        if not text:
            raise RuntimeError("Transcription returned no text from OpenRouter models.")
        raise RuntimeError(
            "Transcription had no timestamps. Set OPENROUTER_WHISPER_MODEL=openai/whisper-1 "
            "or another model that supports verbose_json segments."
        )
    return Transcript(language=getattr(result, "language", language), segments=segments)


def _whisper_openrouter_json(audio: Path, language: str | None) -> Transcript:
    import base64

    import httpx

    from sermon_cut.detect import parse_json
    from sermon_cut.providers import (
        DEFAULT_OPENROUTER_WHISPER,
        OPENROUTER_BASE,
        openrouter_headers,
    )

    model = os.environ.get("OPENROUTER_WHISPER_MODEL", DEFAULT_OPENROUTER_WHISPER)
    payload = {
        "model": model,
        "input_audio": {
            "data": base64.b64encode(audio.read_bytes()).decode("ascii"),
            "format": audio.suffix.lstrip(".").lower() or "mp3",
        },
        "response_format": "verbose_json",
    }
    if language:
        payload["language"] = language
    response = httpx.post(
        f"{OPENROUTER_BASE}/audio/transcriptions",
        json=payload,
        headers=openrouter_headers(),
        timeout=600.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenRouter transcription failed: {response.text[:800]}")
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else parse_json(response.text)
    segments = [
        Segment(float(s["start"]), float(s["end"]), str(s.get("text") or ""))
        for s in data.get("segments") or []
    ]
    if not segments:
        raise RuntimeError(
            "OpenRouter transcription had no timestamps. "
            "Try OPENROUTER_WHISPER_MODEL=openai/whisper-1"
        )
    return Transcript(language=data.get("language") or language, segments=segments)


def _whisper_gemini(audio: Path, language: str | None) -> Transcript:
    """Gemini is weaker at precise timestamps; prefer openai/groq for this step."""
    from sermon_cut.detect import gemini_client

    client = gemini_client()
    uploaded = client.files.upload(file=str(audio))
    lang_hint = f" Language of the service: {language}." if language else ""
    prompt = (
        "Transcribe this church service audio with timestamps."
        f"{lang_hint}\n"
        "Return JSON only: {\"language\":\"pt\",\"segments\":["
        "{\"start\":0.0,\"end\":8.2,\"text\":\"...\"}]}\n"
        "start/end are seconds from the beginning of this audio file. "
        "Keep segments around 10-30 seconds. Transcribe everything, not a summary."
    )
    response = client.models.generate_content(
        model=os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-2.5-flash"),
        contents=[prompt, uploaded],
        config={"response_mime_type": "application/json"},
    )
    from sermon_cut.detect import parse_json

    data = parse_json(response.text or "")
    segments = [
        Segment(
            start=float(s["start"]),
            end=float(s["end"]),
            text=str(s.get("text") or ""),
        )
        for s in data.get("segments", [])
    ]
    return Transcript(language=data.get("language") or language, segments=segments)
