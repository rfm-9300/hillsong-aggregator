# Extractor Deployment Runbook

Triggered when Rodrigo says "make deploy", "make deployment", "deploy to VPS", "make the deployment", "deploy", or any close deployment variant.

This app does **not** deploy to `hillsong-vps`. That host is WhatsApp-bot. Extractor runs on its own VPS.

## Overview

| Component | Runtime | Notes |
|-----------|---------|-------|
| Web | Docker image | `ghcr.io/rfm-9300/hillsong-aggregator:${TAG:-latest}` — FastAPI dashboard on port 8000 |
| Worker | Same image | `python -m app.worker` — processes jobs one at a time |
| Data | Docker volume | `extractor_data` mounted at `/data` (uploads, SQLite, settings, outputs) |
| Caddy | `docker-compose.caddy.yml` | Reverse proxy on this VPS (`:80`, 4GB body limit) |

## Production Target

- SSH alias: `extractor-vps`
- Host: `172.233.116.75` (root, GitHub SSH key)
- Connect with: `ssh extractor-vps`
- Production directory: `~/hillsong-aggregator`
- App compose file: `docker-compose.prod.yml`
- Caddy compose file: `docker-compose.caddy.yml`
- Public URL: `http://172.233.116.75`
- Health endpoint: `/health`

## Preflight

Run from the repo root:

```bash
git status --short
docker info
```

Do not require a clean worktree, but do not overwrite unrelated local changes.

Confirm the production host is reachable:

```bash
ssh extractor-vps "echo ok"
```

## Step 1 - Build and Push Image

Use the repo script:

```bash
./deploy.sh
```

By default this builds and pushes:

```text
ghcr.io/rfm-9300/hillsong-aggregator:latest
```

Override with environment variables only when needed:

```bash
REGISTRY_IMAGE=ghcr.io/rfm-9300/hillsong-aggregator TAG=latest ./deploy.sh
```

## Step 2 - Sync Deploy Files

Ensure the production directory exists:

```bash
ssh extractor-vps "mkdir -p ~/hillsong-aggregator"
```

Copy non-secret deployment files to the VPS:

```bash
scp docker-compose.prod.yml docker-compose.caddy.yml Caddyfile extractor-vps:~/hillsong-aggregator/
```

Do not copy `.env` unless Rodrigo explicitly asks. Production secrets should already live on the VPS.

On first deploy, create `~/hillsong-aggregator/.env` on the VPS with at least `OPENROUTER_API_KEY`, `DASHBOARD_USER`, and `DASHBOARD_PASSWORD`. Ask Rodrigo before writing secrets.

Create the shared proxy network once:

```bash
ssh extractor-vps "docker network create web_proxy || true"
```

## Step 3 - Deploy on VPS

Run:

```bash
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml pull"
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml down"
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml up -d"
```

Leave Caddy running. Only recreate it when `docker-compose.caddy.yml` or `Caddyfile` changed:

```bash
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.caddy.yml up -d"
```

## Step 4 - Verify

Check container state:

```bash
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml ps"
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.caddy.yml ps"
```

Check logs:

```bash
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml logs --tail=100 web"
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml logs --tail=100 worker"
```

Probe health from inside the web container (port 8000 is not published on the host):

```bash
ssh extractor-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml exec web python -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())\""
```

Also probe the public proxy:

```bash
curl -sS -m 15 http://172.233.116.75/health
```

Report success only after web and worker are up, Caddy is up, and the health check passes.

## Public Routing

This VPS is dedicated to Extractor. Caddy listens on `80/443` and proxies to `hillsong-aggregator-web-1:8000` on the private `web_proxy` network. Production compose does not publish port `8000`.

Church videos are large — the Caddyfile already sets `request_body { max_size 4GB }`.

Do not point this app at `hillsong-vps` or `/root/websites-thebots/Caddyfile`. Do not change DNS unless Rodrigo explicitly asks.

## Failure Rules

- If the image pull fails, check image name, registry login, and tag.
- If the web container fails to start, inspect web logs first. Missing `DASHBOARD_USER` / `DASHBOARD_PASSWORD` returns HTTP 503 on the UI.
- If jobs stay queued, inspect worker logs and confirm `OPENROUTER_API_KEY` (or another provider key) is set.
- If public HTTP fails but in-container `/health` works, inspect Caddy and the `web_proxy` network.
- Do not delete Docker volumes, wipe `/data`, or rotate secrets unless Rodrigo explicitly asks.
