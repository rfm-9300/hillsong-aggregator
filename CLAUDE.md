# CLAUDE.md

Sermon extractor. CLI pipeline + FastAPI dashboard.

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

When Rodrigo says "make deploy", "make deployment", "deploy to VPS", "make the deployment", "deploy", or any close deployment variant, follow `DEPLOYMENT_RUNBOOK.md`. Those phrases grant permission to run the full production deployment workflow: execute `./deploy.sh`, connect to `extractor-vps` (`172.233.116.75`), deploy with `docker-compose.prod.yml`, inspect health/logs/status, fix safe deployment issues, and redeploy if needed.

This app does not deploy to `hillsong-vps`.

### Production Host
- SSH alias: `extractor-vps`
- Host: `172.233.116.75`
- Connect with: `ssh extractor-vps`
- Production app directory: `~/hillsong-aggregator`
- Production compose file: `docker-compose.prod.yml`
- Caddy compose file: `docker-compose.caddy.yml`
- Production image: `ghcr.io/rfm-9300/hillsong-aggregator:${TAG:-latest}`
- Public URL: `http://172.233.116.75`

### Deployment Guardrails
- Do not delete the `extractor_data` volume, wipe job outputs, rotate secrets, or run destructive cleanup unless Rodrigo explicitly asks.
- Do not change `.env` or production secrets unless Rodrigo explicitly asks.
- Keep unrelated local worktree changes intact.

## UI Design System

When adding or changing web UI (`app/templates/`, `app/static/`), follow [`design-system/AGENTS.md`](design-system/AGENTS.md). Do not invent a parallel visual language.

## Dashboard

Private admin UI: paste a YouTube link or upload a video, watch job status, download the cut. **Watch** monitors YouTube channels and queues new uploads as jobs. Auth is HTTP Basic (`DASHBOARD_USER` / `DASHBOARD_PASSWORD`). See `README.md`.
