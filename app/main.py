from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.formparsers import MultiPartParser

from app.auth import require_user
from app.config import ALLOWED_SUFFIXES, MAX_UPLOAD_BYTES, UPLOADS_DIR, ensure_dirs
from app.jobs import create_job, get_job, init_db, list_jobs, read_log
from app.progress import build_progress, format_confidence, format_duration
from app.settings import FIELD_BY_KEY
from app.settings import apply as apply_settings
from app.settings import form_groups, provider_status, save_from_form
from sermon_cut.pipeline import TRANSCRIPT_SOURCES
from sermon_cut.youtube import is_url

try:
    MultiPartParser.max_part_size = MAX_UPLOAD_BYTES
except AttributeError:
    pass

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    init_db()
    apply_settings()
    yield


app = FastAPI(title="Podcast aggregator", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^\w.\- ]+", "_", base).strip("._") or "video"
    return cleaned[:180]


def _form_page(request: Request, error: str, status_code: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"jobs": list_jobs(), "error": error},
        status_code=status_code,
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request, _: str = Depends(require_user)):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"jobs": list_jobs(), "error": None},
    )


@app.post("/jobs")
async def create_job_route(
    request: Request,
    video: UploadFile | None = File(None),
    url: str = Form(""),
    language: str = Form(""),
    transcript_source: str = Form("auto"),
    pad_start: float = Form(2.0),
    pad_end: float = Form(5.0),
    reencode: bool = Form(False),
    _: str = Depends(require_user),
):
    url = url.strip()
    has_upload = video is not None and bool((video.filename or "").strip())
    if url and has_upload:
        return _form_page(request, "Give either a link or a file, not both.")
    if not url and not has_upload:
        return _form_page(request, "Paste a video link or choose a file to upload.")
    if transcript_source not in TRANSCRIPT_SOURCES:
        transcript_source = "auto"

    job_id = uuid.uuid4().hex

    if url:
        if not is_url(url):
            return _form_page(request, "That does not look like a link. Use a full http(s) URL.")
        create_job(
            job_id=job_id,
            source_type="url",
            source_url=url,
            language=language.strip() or None,
            transcript_source=transcript_source,
            pad_start=pad_start,
            pad_end=pad_end,
            reencode=reencode,
        )
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    assert video is not None
    original = _safe_filename(video.filename or "video.mp4")
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return _form_page(
            request,
            f"Unsupported file type {suffix or '(none)'}. Use: {', '.join(sorted(ALLOWED_SUFFIXES))}",
        )

    dest = UPLOADS_DIR / f"{job_id}_{original}"
    size = 0
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as handle:
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload too large")
                handle.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        await video.close()

    if size == 0:
        dest.unlink(missing_ok=True)
        return _form_page(request, "The uploaded file was empty.")

    create_job(
        job_id=job_id,
        source_type="upload",
        filename=original,
        source_path=dest,
        language=language.strip() or None,
        transcript_source=transcript_source,
        pad_start=pad_start,
        pad_end=pad_end,
        reencode=reencode,
    )
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: str, _: str = Depends(require_user)):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    log = read_log(job_id)
    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "job": job,
            "log": log,
            "progress": build_progress(status=job.status, log=log),
            "format_duration": format_duration,
            "format_confidence": format_confidence,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, _: str = Depends(require_user)):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "groups": form_groups(),
            "providers": provider_status(),
            "saved": False,
            "error": None,
        },
    )


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(request: Request, _: str = Depends(require_user)):
    form = await request.form()
    values = {
        key: value
        for key in FIELD_BY_KEY
        if isinstance((value := form.get(key)), str)
    }
    save_from_form(values)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "groups": form_groups(),
            "providers": provider_status(),
            "saved": True,
            "error": None,
        },
    )


@app.get("/jobs/{job_id}/download")
def download_job(job_id: str, _: str = Depends(require_user)):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or not job.output_exists:
        raise HTTPException(status_code=404, detail="Output not ready")
    return FileResponse(
        path=job.output_path,
        filename=job.download_name,
        media_type="video/mp4",
    )


@app.get("/jobs/{job_id}/media")
def stream_job(job_id: str, _: str = Depends(require_user)):
    """Inline playback for the in-page player."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or not job.output_exists:
        raise HTTPException(status_code=404, detail="Output not ready")
    return FileResponse(
        path=job.output_path,
        media_type="video/mp4",
        filename=job.download_name,
        content_disposition_type="inline",
    )
