# CLAUDE.md

Sermon extractor. CLI pipeline + FastAPI dashboard.

## UI Design System

When adding or changing web UI (`app/templates/`, `app/static/`), follow [`design-system/AGENTS.md`](design-system/AGENTS.md). Do not invent a parallel visual language.

## Dashboard

Private admin UI: paste a YouTube link or upload a video, watch job status, download the cut. Auth is HTTP Basic (`DASHBOARD_USER` / `DASHBOARD_PASSWORD`). See `README.md`.
