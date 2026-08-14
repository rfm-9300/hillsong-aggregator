# Hillsong Aggregator Deployment Runbook

Triggered when Rodrigo says "make deploy", "make deployment", "deploy to VPS", "make the deployment", "deploy", or any close deployment variant.

## Overview

| Component | Runtime | Notes |
|-----------|---------|-------|
| Web | Docker image | `ghcr.io/rfm-9300/hillsong-aggregator:${TAG:-latest}` — FastAPI dashboard on port 8000 |
| Worker | Same image | `python -m app.worker` — processes jobs one at a time |
| Data | Docker volume | `extractor_data` mounted at `/data` (uploads, SQLite, settings, outputs) |
| Website Caddy | Existing VPS container | Reverse proxy and TLS for public access |

## Production Target

- SSH alias: `hillsong-vps`
- Production directory: `~/hillsong-aggregator`
- Compose file: `docker-compose.prod.yml`
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
ssh hillsong-vps "echo ok"
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
ssh hillsong-vps "mkdir -p ~/hillsong-aggregator"
```

Copy non-secret deployment files to the VPS:

```bash
scp docker-compose.prod.yml hillsong-vps:~/hillsong-aggregator/
```

Do not copy `.env` unless Rodrigo explicitly asks. Production secrets should already live on the VPS.

On first deploy, create `~/hillsong-aggregator/.env` on the VPS with at least `OPENROUTER_API_KEY`, `DASHBOARD_USER`, and `DASHBOARD_PASSWORD`. Ask Rodrigo before writing secrets.

## Step 3 - Deploy on VPS

Run:

```bash
ssh hillsong-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml pull"
ssh hillsong-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml down"
ssh hillsong-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml up -d"
```

## Step 4 - Verify

Check container state:

```bash
ssh hillsong-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml ps"
```

Check logs:

```bash
ssh hillsong-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml logs --tail=100 web"
ssh hillsong-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml logs --tail=100 worker"
```

Probe health from inside the web container (port 8000 is not published on the host):

```bash
ssh hillsong-vps "cd ~/hillsong-aggregator && docker compose -f docker-compose.prod.yml exec web python -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())\""
```

Report success only after both containers are up and the health check passes.

## Public Routing

The VPS already runs the `websites-thebots-web` Caddy container on ports `80/443`. Production compose does not publish port `8000`; public traffic reaches the dashboard through the private `web_proxy` Docker network shared with Caddy.

Create the shared proxy network once:

```bash
ssh hillsong-vps "docker network create web_proxy || true"
```

Add a host route to `/root/websites-thebots/Caddyfile` when exposing the dashboard. Church videos are large, so raise the body limit:

```caddy
aggregator.thebotslab.eu {
  request_body {
    max_size 4GB
  }
  reverse_proxy hillsong-aggregator-web-1:8000
}
```

DNS for `aggregator.thebotslab.eu` must point at the VPS. Then reload the website Caddy container:

```bash
ssh hillsong-vps "cd ~/websites-thebots && docker compose exec web caddy reload --config /etc/caddy/Caddyfile"
```

Do not change the live Caddyfile or DNS unless Rodrigo explicitly asks.

## Failure Rules

- If the image pull fails, check image name, registry login, and tag.
- If the web container fails to start, inspect web logs first. Missing `DASHBOARD_USER` / `DASHBOARD_PASSWORD` returns HTTP 503 on the UI.
- If jobs stay queued, inspect worker logs and confirm `OPENROUTER_API_KEY` (or another provider key) is set.
- Do not delete Docker volumes, wipe `/data`, or rotate secrets unless Rodrigo explicitly asks.
