# Extractor

Sermon extractor dashboard and CLI. Web UI follows [`design-system/AGENTS.md`](design-system/AGENTS.md).

## Commands

- `uvicorn app.main:app --reload --port 8000` — dashboard
- `python -m app.worker` — job worker
- `python3 extract_sermon.py "…"` — CLI (see README.md)

## UI Design System

When adding or changing `app/templates/` or `app/static/`, follow [`design-system/AGENTS.md`](design-system/AGENTS.md). Tokens and classes match the thebots.lab / WhatsApp-bot system. Compact shell (topbar + view), one stylesheet: `app/static/style.css`.
