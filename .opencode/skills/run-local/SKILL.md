---
name: run-local
description: Start the Sermon Extractor dashboard locally (FastAPI web app + background worker), verify Docker health and the /health endpoint, inspect logs, and fix common local startup failures. Use this whenever the user says "run it locally", "start the app", "boot the dev env", "is it running", "check the logs", or asks to verify, restart, or fix the local stack.
---

# Run Local

Project-specific runbook for the Sermon Extractor dashboard. The normal local stack is two Docker Compose services that share the host `./data` directory:

- **web**: FastAPI dashboard on port `8000`
- **worker**: processes one queued video-extraction job at a time

The web service needs `ffmpeg` and the worker needs a configured LLM provider key when processing jobs. The `/health` endpoint only verifies that the web app is running; it does not test credentials or the worker.

All paths below are relative to the repository root (`/Users/rodrigomartins/projects/Extractor`).

## When to use

Trigger on any of these:

- User asks to start, run, boot, launch, or spin up the dashboard or local environment
- User asks whether the dashboard is running, healthy, or available
- User asks to inspect or tail dashboard or worker logs
- User reports that a local upload or extraction job is stuck, crashes, or fails
- After code changes, user wants to verify the running stack

If the user only wants to run the CLI extractor, do not start Docker. Use `python3 extract_sermon.py <video>` after checking that `.env` contains a provider key and `ffmpeg` is installed.

## Workflow

### 1. Pre-flight checks

Run these checks before starting services:

```bash
test -f .env && echo "env: ok" || echo "env: MISSING"
docker info >/dev/null 2>&1 && echo "docker: ok" || echo "docker: NOT RUNNING"
lsof -i :8000 -sTCP:LISTEN -n -P
docker compose ps
```

Decisions:

- **No `.env`**: run `cp .env.example .env`, then stop and tell the user to set `OPENROUTER_API_KEY`, `DASHBOARD_USER`, and `DASHBOARD_PASSWORD`. Do not overwrite an existing `.env`.
- **Docker is not running**: ask the user to start Docker Desktop. Do not launch it automatically.
- **Port 8000 is in use**: use `docker compose ps` and `lsof` to identify the owner. Stop it only if it is this project's stale `web` container; otherwise ask before touching it.
- **Existing services are already healthy**: do not rebuild or restart them unless the user asked for a restart.

### 2. Start the Docker stack

Start or rebuild both services in the background:

```bash
docker compose up --build -d
```

Confirm Compose started both services:

```bash
docker compose ps
```

If image construction fails, inspect the build output. The image installs `ffmpeg` and Python dependencies from `requirements.txt`; do not suppress a failed build.

### 3. Verify startup

Wait up to about 60 seconds for the web app, then probe its health endpoint:

```bash
curl -fsS http://localhost:8000/health
docker compose ps
```

Success requires:

- `curl` returns `{"status":"ok"}`
- `web` is running and eventually reports `healthy`
- `worker` is running

Open `http://localhost:8000` in a browser only after `/health` passes. The dashboard uses HTTP Basic authentication; use `DASHBOARD_USER` and `DASHBOARD_PASSWORD` from `.env`.

### 4. Inspect logs and jobs

Use the least noisy command that answers the question:

```bash
docker compose logs --tail=100 web
docker compose logs --tail=100 worker
docker compose logs -f web worker
```

For an individual extraction job, its detailed pipeline log is stored in `data/logs/<job-id>.log`. Service logs identify the job ID when it starts or fails.

An idle worker prints `Worker waiting for jobs...`. A running worker prints `Running job <id> (<filename>)`; it processes only one job at a time by design.

### 5. Report

Tell the user concisely:

- Web: running on `http://localhost:8000` and the `/health` response
- Worker: running or the relevant failure
- Any warnings or failures in recent web/worker logs
- For extraction failures, the job ID and the relevant `data/logs/<job-id>.log` location

Leave the stack running unless the user asked to stop it.

## Native development alternative

Use this only when the user explicitly wants to run without Docker or needs live reload while editing the FastAPI app.

Preconditions:

```bash
source .venv/bin/activate
pip install -r requirements.txt
ffmpeg -version
```

Start the web app and worker as separate background processes:

```bash
uvicorn app.main:app --reload --port 8000
python -m app.worker
```

Then verify with:

```bash
curl -fsS http://localhost:8000/health
```

Native mode writes state to the same default `./data` directory as Docker. Do not run native and Docker workers together unless intentionally testing concurrency: they share the SQLite queue and output directories.

## Stopping the stack

```bash
docker compose down
```

This stops containers but preserves `./data`, including uploaded videos, SQLite state, logs, work files, and completed sermon cuts. Never use `docker compose down -v` or delete `./data` without explicit user approval.

For native mode, stop only the background `uvicorn` and `python -m app.worker` processes started for this session. Do not kill an unknown process merely because it owns port `8000`.

## Common failures and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker: NOT RUNNING` | Docker Desktop is stopped | Ask the user to start Docker Desktop, then retry. |
| `port is already allocated` / bind error on `8000` | Another local service or a stale Extractor container owns the port | Identify it with `lsof` and `docker compose ps`; stop only this project's stale service. |
| `web` exits immediately | Bad environment, import error, or failed application startup | Read `docker compose logs --tail=100 web`; fix the reported issue and restart the stack. |
| `worker` exits immediately | Import/configuration failure | Read `docker compose logs --tail=100 worker`; fix the reported issue and restart the worker. |
| Dashboard returns `503` saying credentials are not configured | `DASHBOARD_USER` or `DASHBOARD_PASSWORD` is empty | Set both values in `.env`, then `docker compose up -d --force-recreate web`. |
| Dashboard returns `401` | Incorrect browser credentials | Use the current `DASHBOARD_USER` and `DASHBOARD_PASSWORD` from `.env`. |
| Job fails with `No provider API key configured` or authentication errors | Missing or invalid LLM API key | Set a valid `OPENROUTER_API_KEY` or another supported provider key in `.env`, then recreate the worker. |
| Job fails around ffmpeg | Damaged image build or invalid input media | Rebuild with `docker compose up --build -d`; inspect the job log for the ffmpeg command and input error. |
| Job remains queued | Worker is stopped or another job is running | Check `docker compose ps` and worker logs. Start the worker or wait for the current job to finish. |
| Job remains `running` after a restart | Previous worker stopped mid-job | Restart the worker; it requeues stale running jobs during startup. |
| SQLite `database is locked` | Multiple workers or native/Docker modes share `./data` | Stop the duplicate worker and use one stack at a time. |

## Boundaries

- Never overwrite `.env` or expose its secret values.
- Never delete `data/`, uploads, outputs, or SQLite state without explicit approval.
- Do not kill processes or containers outside this project.
- Small, obvious fixes to startup configuration are acceptable. Stop and ask before making architectural or credential-provider changes.
- If the same startup problem persists after two attempted fixes, summarize evidence and ask the user rather than looping.
