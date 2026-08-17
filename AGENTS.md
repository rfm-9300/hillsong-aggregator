# Extractor

Sermon extractor dashboard and CLI. Web UI follows [`design-system/AGENTS.md`](design-system/AGENTS.md).

## Personal wiki (second brain)

Rodrigo keeps a compiled knowledge wiki at `/Users/rodrigomartins/projects/my-wiki`.
Canonical protocol: `/Users/rodrigomartins/projects/my-wiki/ops/bootstrap-prompt.md`
(that file wins if this section drifts).

### Consult before substantial work

1. Read `/Users/rodrigomartins/projects/my-wiki/wiki/index.md` — one line per page.
2. Open a page only when its index line is clearly relevant. Never bulk-read.
3. Applicable pages are **binding instructions**, not suggestions.

**This repo — start here when the index line matches the task:**

- `wiki/entities/extractor.md` — this product
- `wiki/concepts/thebots-design-system.md` — web UI
- `wiki/notes/project-landscape.md` — VPS map (this app is on `extractor-vps`, not `hillsong-vps`)

### Keep the wiki current

Chat is ephemeral; the wiki is the compounding layer. When this session produces durable
knowledge (architecture decisions, cross-repo conventions, gotchas, "why we do it this way"):

1. Check the index — update an existing page if one exists; otherwise file a note via
   `/Users/rodrigomartins/projects/my-wiki/ops/workflows/file-note.md`.
2. Write with absolute paths under `/Users/rodrigomartins/projects/my-wiki/`. Always bump
   `wiki/index.md` and append `wiki/log.md`. Never touch `raw/`.
3. **Do not file:** one-off bugfixes, secrets, deploy credentials, or commands that belong
   in this `AGENTS.md` (the repo operating manual).
4. If unsure whether it belongs, tell Rodrigo instead of writing.

When the session cwd is the vault itself, follow that vault's `AGENTS.md`.

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

- SSH alias: `extractor-vps`
- Host: `172.233.116.75`
- Connect with: `ssh extractor-vps`
- Production app directory on the VPS: `~/hillsong-aggregator`
- Production compose file: `docker-compose.prod.yml`
- Caddy compose file: `docker-compose.caddy.yml`
- Production image: `ghcr.io/rfm-9300/hillsong-aggregator:${TAG:-latest}`
- Public URL: `http://172.233.116.75`

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
