# Extractor

Sermon extractor dashboard and CLI. Web UI follows [`design-system/AGENTS.md`](design-system/AGENTS.md).

## Deployment Intent

When Rodrigo says any of the following, treat it as permission to execute the full production deployment workflow for this project:

- "make deploy"
- "make deployment"
- "deploy to VPS"
- "make the deployment"
- "deploy"
- any close variant that clearly means deploying this extractor to production

Use [DEPLOYMENT_RUNBOOK.md](DEPLOYMENT_RUNBOOK.md) as the source of truth.

## Production Host

- SSH alias: `hillsong-vps`
- Connect with: `ssh hillsong-vps`
- Production app directory on the VPS: `~/hillsong-aggregator`
- Production compose file: `docker-compose.prod.yml`
- Production image: `ghcr.io/rfm-9300/hillsong-aggregator:${TAG:-latest}`

## Deployment Rules

- Use the existing `./deploy.sh` script from the repo root to build and push the Docker image.
- Use `docker compose -f docker-compose.prod.yml` on the VPS.
- Prefer the safe deploy sequence: `pull`, `down`, `up -d`.
- After deploying, check container state, `/health`, and web/worker logs before reporting success.
- If deployment fails, diagnose the concrete failure, apply the smallest safe fix, then redeploy.
- Do not delete the `extractor_data` volume, wipe job outputs, rotate secrets, or run destructive cleanup unless Rodrigo explicitly asks.
- Do not change `.env` or production secrets unless Rodrigo explicitly asks.
- Keep unrelated local worktree changes intact.

## Commands

- `uvicorn app.main:app --reload --port 8000` — dashboard
- `python -m app.worker` — job worker
- `python3 extract_sermon.py "…"` — CLI (see README.md)

## UI Design System

When adding or changing `app/templates/` or `app/static/`, follow [`design-system/AGENTS.md`](design-system/AGENTS.md). Tokens and classes match the thebots.lab / WhatsApp-bot system. Compact shell (topbar + view), one stylesheet: `app/static/style.css`.
