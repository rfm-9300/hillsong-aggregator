from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass

from sermon_cut.providers import (
    DEFAULT_OPENROUTER_MODEL,
    openrouter_client,
    require_env,
)
from sermon_cut.transcript import Transcript, fmt_ts, parse_ts

DETECT_PROMPT = """You are cutting a full church meeting recording down to the MAIN SERMON only.

The recording usually contains several parts, in any language (often Portuguese or English):
- welcome / host remarks
- worship songs and singing
- announcements, offering, testimonies
- the sermon / preaching / Bible teaching (THIS is what we want)
- response, altar call, ministry time that is still part of the sermon close
- final worship, greetings, credits

Identify the start and end of the main sermon:
- START: when the preacher begins the message itself (scripture reading that opens the sermon, "open your Bibles", first teaching sentence). Skip worship and announcements.
- END: when the sermon and its immediate closing prayer / amen are finished. Cut before the final song set, goodbye, or credits. If there is a short response/altar call that belongs to this sermon, include it.

Return JSON only with this shape:
{
  "sermon_found": true,
  "start_seconds": 1234.0,
  "end_seconds": 4567.0,
  "confidence": 0.0,
  "title": "short title if you can infer one, else empty string",
  "reasoning": "one short paragraph citing transcript cues you used"
}

Rules:
- start_seconds and end_seconds must come from the transcript timestamps, not guesses far outside them.
- If no sermon is present, set sermon_found to false and still give your best window or zeros.
- Do not include long worship blocks before or after the preaching.
"""


@dataclass
class SermonWindow:
    sermon_found: bool
    start_seconds: float
    end_seconds: float
    confidence: float
    title: str
    reasoning: str

    def clamped(self, duration: float, pad_start: float, pad_end: float) -> "SermonWindow":
        start = max(0.0, self.start_seconds - pad_start)
        end = min(duration, self.end_seconds + pad_end)
        if end <= start:
            end = min(duration, start + 1.0)
        return SermonWindow(
            sermon_found=self.sermon_found,
            start_seconds=start,
            end_seconds=end,
            confidence=self.confidence,
            title=self.title,
            reasoning=self.reasoning,
        )

    def as_dict(self) -> dict:
        data = asdict(self)
        data["start"] = fmt_ts(self.start_seconds)
        data["end"] = fmt_ts(self.end_seconds)
        data["duration_seconds"] = round(self.end_seconds - self.start_seconds, 3)
        return data


def detect_from_transcript(transcript: Transcript, llm: str) -> SermonWindow:
    body = transcript.as_prompt()
    if not body.strip():
        raise RuntimeError("Transcript is empty; cannot detect the sermon.")
    user = (
        f"Detected language: {transcript.language or 'unknown'}\n\n"
        f"Timestamped transcript:\n\n{body}"
    )
    raw = _complete_json(llm, DETECT_PROMPT, user)
    return _window_from_payload(raw)


def _complete_json(llm: str, system: str, user: str) -> dict:
    if llm == "openai":
        return _openai_json(system, user)
    if llm == "openrouter":
        return _openrouter_json(system, user)
    if llm == "groq":
        return _groq_json(system, user)
    if llm == "gemini":
        return _gemini_json(system, user)
    if llm == "anthropic":
        return _anthropic_json(system, user)
    raise ValueError(f"Unsupported LLM: {llm}")


def _openrouter_json(system: str, user: str) -> dict:
    client = openrouter_client()
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except Exception:
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=messages,
        )
    return parse_json(response.choices[0].message.content or "")


def _openai_json(system: str, user: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=require_env("OPENAI_API_KEY"))
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return parse_json(response.choices[0].message.content or "")


def _groq_json(system: str, user: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=require_env("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return parse_json(response.choices[0].message.content or "")


def gemini_client():
    from google import genai

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set")
    return genai.Client(api_key=key)


def _gemini_json(system: str, user: str) -> dict:
    client = gemini_client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    response = client.models.generate_content(
        model=model,
        contents=f"{system}\n\n{user}",
        config={"response_mime_type": "application/json"},
    )
    return parse_json(response.text or "")


def _anthropic_json(system: str, user: str) -> dict:
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(api_key=key)
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return parse_json(text)


def parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise RuntimeError(f"Model did not return JSON:\n{text[:800]}")
        return json.loads(match.group(0))


def _window_from_payload(data: dict) -> SermonWindow:
    start = data.get("start_seconds", data.get("start"))
    end = data.get("end_seconds", data.get("end"))
    if start is None or end is None:
        raise RuntimeError(f"Model JSON missing start/end: {data}")
    return SermonWindow(
        sermon_found=bool(data.get("sermon_found", True)),
        start_seconds=parse_ts(start),
        end_seconds=parse_ts(end),
        confidence=float(data.get("confidence") or 0.0),
        title=str(data.get("title") or ""),
        reasoning=str(data.get("reasoning") or ""),
    )
