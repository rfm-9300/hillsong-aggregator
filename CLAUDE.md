# CLAUDE.md

Sermon extractor. CLI pipeline + FastAPI dashboard.

## Deployment Intent

When Rodrigo says "make deploy", "make deployment", "deploy to VPS", "make the deployment", "deploy", or any close deployment variant, follow `DEPLOYMENT_RUNBOOK.md`. Those phrases grant permission to run the full production deployment workflow: execute `./deploy.sh`, connect to `hillsong-vps`, deploy with `docker-compose.prod.yml`, inspect health/logs/status, fix safe deployment issues, and redeploy if needed.

### Production Host
- SSH alias: `hillsong-vps`
- Connect with: `ssh hillsong-vps`
- Production app directory: `~/hillsong-aggregator`
- Production compose file: `docker-compose.prod.yml`
- Production image: `ghcr.io/rfm-9300/hillsong-aggregator:${TAG:-latest}`

### Deployment Guardrails
- Do not delete the `extractor_data` volume, wipe job outputs, rotate secrets, or run destructive cleanup unless Rodrigo explicitly asks.
- Do not change `.env` or production secrets unless Rodrigo explicitly asks.
- Keep unrelated local worktree changes intact.

## UI Design System

When adding or changing web UI (`app/templates/`, `app/static/`), follow [`design-system/AGENTS.md`](design-system/AGENTS.md). Do not invent a parallel visual language.

## Dashboard

Private admin UI: paste a YouTube link or upload a video, watch job status, download the cut. Auth is HTTP Basic (`DASHBOARD_USER` / `DASHBOARD_PASSWORD`). See `README.md`.
