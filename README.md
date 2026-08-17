# Sermon extractor

Takes a full church-service video, finds the main sermon, and writes a trimmed video.

Give it a local file or a YouTube link.

Pipeline:

1. `ffmpeg` extracts mono 16 kHz audio
2. Whisper transcribes it with timestamps (OpenRouter by default)
3. An LLM reads the timestamped transcript and returns sermon start/end
4. `ffmpeg` cuts that window out of the original video

## YouTube links skip the expensive step

When a video already has captions, step 1 and 2 are unnecessary: the captions already carry timestamps, so they go straight to the cheap text LLM in step 3. No audio extraction, no Whisper.

`--transcript-source` controls this for links:

| Value | Behaviour |
| --- | --- |
| `auto` (default) | Reuse captions when they exist, otherwise fall back to Whisper |
| `captions` | Captions only; fail rather than pay for Whisper |
| `whisper` | Ignore captions and always transcribe the audio |

Published (human) captions win over auto-generated ones, and the spoken language wins over translations. Pass `--language pt` to force a specific track.

A dry run on a captioned link never downloads the video at all:

```bash
python3 extract_sermon.py "https://www.youtube.com/watch?v=…" --dry-run
```

## Setup

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Put your OpenRouter key in `.env`:

```
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=google/gemini-2.5-flash
OPENROUTER_WHISPER_MODEL=openai/whisper-large-v3
```

Other keys (`OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`) still work if you want them.

## Usage

```bash
python3 extract_sermon.py "service.mp4"
python3 extract_sermon.py "service.mp4" -o sermon.mp4 --language pt
python3 extract_sermon.py "service.mp4" --dry-run --keep-work
python3 extract_sermon.py "service.mp4" --model openai/gpt-4o-mini

python3 extract_sermon.py "https://www.youtube.com/watch?v=…"
python3 extract_sermon.py "https://www.youtube.com/watch?v=…" --transcript-source captions
python3 extract_sermon.py "https://www.youtube.com/watch?v=…" --transcript-source whisper --language pt
```

`--reencode` if the fast copy cut lands on a bad keyframe. `--pad-start` / `--pad-end` add a few seconds of buffer around the detected window.

## Dashboard (Docker)

The FastAPI dashboard is a private admin UI: paste a YouTube link or upload a service video, watch job status, download the cut sermon. A worker runs jobs one at a time. The job page shows which transcript source was used, so you can see when a run cost nothing but the text LLM call.

On **Watch**, add YouTube channel URLs. The dashboard (and worker) poll for new uploads and queue each one as a normal link job. Videos already on the channel when you add it are skipped; use **Queue latest** to process the current upload. Live and upcoming videos wait until they are published. Shorts under the skip threshold (default 3 minutes) are ignored.

On **Edit**, upload intro and ending clips and select which ones are active. When a job finishes, the worker stitches `intro → sermon → ending` into the final downloadable video. You can rebuild an older job with the current branding from the job page.

The dashboard UI follows [`design-system/`](design-system/README.md) (same thebots.lab tokens and classes as WhatsApp-bot). Light/dark toggle is in the top bar.

1. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`, `DASHBOARD_USER`, and `DASHBOARD_PASSWORD`.
2. Start both services:

```bash
docker compose up --build
```

3. Open `http://localhost:8000` and sign in with the dashboard credentials.

Keys and models can be changed later on **Settings**. That page writes `data/settings.json` on the host volume and the worker reloads it before each job, so you do not rebuild the image to rotate a key or switch a model. Values saved there override `.env`. Leave a secret field blank to keep the current key; clear a model field to fall back to `.env` / the built-in default.

Uploads, SQLite, settings, logs, and outputs live in `./data` on the host.

Production deploys to `extractor-vps` (`172.233.116.75`) from `ghcr.io/rfm-9300/hillsong-aggregator`. Public URL: `http://172.233.116.75`. See [`DEPLOYMENT_RUNBOOK.md`](DEPLOYMENT_RUNBOOK.md). Church videos are large — Caddy on that VPS already allows `request_body { max_size 4GB }`. Link jobs sidestep the upload limit entirely, since the server downloads the video itself.

Optional link settings in `.env`: `YTDLP_FORMAT` to prefer H.264/AAC up to 1080p (keeps intro/ending packaging fast; AV1 downloads are slow to re-encode), `YTDLP_COOKIES_FILE` for members-only videos. YouTube changes often, so rebuild now and then to pick up a newer `yt-dlp`.

Locally without Docker:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
python -m app.worker
```
