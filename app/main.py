from __future__ import annotations

import re
import threading
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.formparsers import MultiPartParser

from app.assets import (
    KINDS,
    add_asset,
    delete_asset,
    load_edit,
    set_active,
    active_package_paths,
)
from app.auth import require_user
from app.config import (
    ALLOWED_SUFFIXES,
    ASSETS_DIR,
    MAX_UPLOAD_BYTES,
    OUTPUTS_DIR,
    UPLOADS_DIR,
    ensure_dirs,
)
from app.jobs import (
    create_job,
    get_job,
    init_db,
    list_jobs,
    log_path,
    mark_failed,
    mark_running,
    read_log,
    update_package,
)
from app.progress import build_progress, format_confidence, format_duration
from app.settings import FIELD_BY_KEY
from app.settings import apply as apply_settings
from app.settings import form_groups, provider_status, save_from_form
from sermon_cut.media import package_sermon
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


async def _save_upload(upload: UploadFile, dest: Path) -> int:
    size = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Upload too large")
            handle.write(chunk)
    return size


def _edit_page(
    request: Request,
    *,
    saved: bool = False,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    config = load_edit()
    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "edit": config,
            "intros": config.assets_of("intro"),
            "outros": config.assets_of("outro"),
            "saved": saved,
            "error": error,
        },
        status_code=status_code,
    )


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
    try:
        size = await _save_upload(video, dest)
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
    edit = load_edit()
    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "job": job,
            "log": log,
            "progress": build_progress(status=job.status, log=log),
            "format_duration": format_duration,
            "format_confidence": format_confidence,
            "can_repackage": bool(
                (
                    job.sermon_exists
                    or (OUTPUTS_DIR / f"{job.id}_sermon.mp4").is_file()
                )
                and job.status in {"done", "failed"}
                and (edit.active_intro or edit.active_outro or job.is_packaged)
            ),
            "edit": edit,
        },
    )


def _resolve_sermon(job) -> Path | None:
    sermon = job.sermon_file
    if sermon is not None:
        return sermon
    candidate = OUTPUTS_DIR / f"{job.id}_sermon.mp4"
    return candidate if candidate.is_file() else None


def _run_repackage(job_id: str, sermon: Path) -> None:
    log = log_path(job_id)
    try:
        intro, outro, meta = active_package_paths()
        final_out = OUTPUTS_DIR / f"{job_id}.mp4"
        with log.open("a", encoding="utf-8") as handle:
            labels = []
            if intro:
                labels.append(f"intro={meta.get('intro_title') or intro.name}")
            if outro:
                labels.append(f"ending={meta.get('outro_title') or outro.name}")
            if labels:
                handle.write(f"Packaging final video ({', '.join(labels)})…\n")
            else:
                handle.write("No intro/ending selected; copying sermon cut as final video.\n")
            handle.flush()

        # Capture package_sermon prints into the job log.
        import sys

        class _LogWriter:
            def __init__(self, path: Path):
                self._path = path

            def write(self, data: str) -> int:
                if not data:
                    return 0
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(data)
                    handle.flush()
                return len(data)

            def flush(self) -> None:
                return None

        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = _LogWriter(log)
        try:
            if intro or outro:
                package_sermon(sermon, final_out, intro=intro, outro=outro)
                package = meta
            else:
                if sermon.resolve() != final_out.resolve():
                    import shutil

                    shutil.copy2(sermon, final_out)
                package = None
        finally:
            sys.stdout, sys.stderr = old_out, old_err

        update_package(
            job_id,
            output_path=final_out,
            sermon_path=sermon,
            package=package,
            mark_done_status=True,
        )
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"Wrote packaged video {final_out}\n")
    except Exception as exc:
        mark_failed(job_id, str(exc))
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"\nerror: {exc}\n")
            handle.write(traceback.format_exc())


@app.post("/jobs/{job_id}/repackage")
def repackage_job(job_id: str, _: str = Depends(require_user)):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "running":
        # Already packaging (or a full job is in progress) — just return to the page.
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
    if job.status not in {"done", "failed"}:
        raise HTTPException(status_code=400, detail="Job is not ready")
    sermon = _resolve_sermon(job)
    if sermon is None:
        raise HTTPException(status_code=404, detail="Sermon cut missing")

    mark_running(
        job.id,
        note="Rebuild requested: adding current intro & ending in the background…",
    )
    threading.Thread(
        target=_run_repackage,
        args=(job.id, sermon),
        name=f"repackage-{job.id}",
        daemon=True,
    ).start()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/edit", response_class=HTMLResponse)
def edit_page(request: Request, _: str = Depends(require_user)):
    return _edit_page(request)


@app.post("/edit/upload")
async def edit_upload(
    request: Request,
    kind: str = Form(...),
    title: str = Form(""),
    video: UploadFile = File(...),
    _: str = Depends(require_user),
):
    if kind not in KINDS:
        return _edit_page(request, error="Choose intro or ending.", status_code=400)
    original = _safe_filename(video.filename or f"{kind}.mp4")
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return _edit_page(
            request,
            error=f"Unsupported file type {suffix or '(none)'}. Use: {', '.join(sorted(ALLOWED_SUFFIXES))}",
            status_code=400,
        )

    ensure_dirs()
    tmp = ASSETS_DIR / f"_upload_{uuid.uuid4().hex}{suffix}"
    try:
        size = await _save_upload(video, tmp)
        if size == 0:
            return _edit_page(request, error="The uploaded file was empty.", status_code=400)
        add_asset(kind=kind, source=tmp, filename=original, title=title.strip())  # type: ignore[arg-type]
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        await video.close()
        tmp.unlink(missing_ok=True)

    return RedirectResponse(url="/edit", status_code=303)


@app.post("/edit/select")
async def edit_select(
    request: Request,
    kind: str = Form(...),
    asset_id: str = Form(""),
    _: str = Depends(require_user),
):
    if kind not in KINDS:
        return _edit_page(request, error="Choose intro or ending.", status_code=400)
    try:
        set_active(kind, asset_id.strip() or None)  # type: ignore[arg-type]
    except ValueError as exc:
        return _edit_page(request, error=str(exc), status_code=400)
    return RedirectResponse(url="/edit", status_code=303)


@app.post("/edit/delete")
async def edit_delete(
    request: Request,
    asset_id: str = Form(...),
    _: str = Depends(require_user),
):
    try:
        delete_asset(asset_id)
    except ValueError as exc:
        return _edit_page(request, error=str(exc), status_code=400)
    return RedirectResponse(url="/edit", status_code=303)


@app.get("/assets/{asset_id}/media")
def stream_asset(asset_id: str, _: str = Depends(require_user)):
    asset = load_edit().get(asset_id)
    if asset is None or not asset.exists:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(
        path=asset.file_path,
        media_type="video/mp4",
        filename=asset.filename,
        content_disposition_type="inline",
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
