from __future__ import annotations

import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from app.config import OUTPUTS_DIR, WORK_DIR, WORKER_POLL_SECONDS, ensure_dirs
from app.settings import apply as apply_settings
from app.jobs import (
    claim_next_job,
    init_db,
    log_path,
    mark_done,
    mark_failed,
    requeue_stale_running,
)
from sermon_cut.pipeline import RunConfig, run


class _FlushWriter:
    def __init__(self, stream):
        self._stream = stream

    def write(self, data: str) -> int:
        n = self._stream.write(data)
        self._stream.flush()
        return n

    def flush(self) -> None:
        self._stream.flush()


@contextmanager
def _capture_logs(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        writer = _FlushWriter(handle)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = writer
        try:
            yield
        finally:
            sys.stdout, sys.stderr = old_out, old_err


def process_job(job) -> None:
    output = OUTPUTS_DIR / f"{job.id}.mp4"
    work = WORK_DIR / job.id
    log = log_path(job.id)

    video: Path | None = None
    if job.source_type == "upload":
        video = Path(job.source_path or "")
        if not video.is_file():
            raise FileNotFoundError(f"Upload missing: {video}")

    apply_settings()
    with _capture_logs(log):
        print(f"Job {job.id}: {job.source_label}")
        result = run(
            RunConfig(
                video=video,
                url=job.source_url if job.source_type == "url" else None,
                output=output,
                language=job.language or None,
                transcript_source=job.transcript_source,
                pad_start=job.pad_start,
                pad_end=job.pad_end,
                reencode=job.reencode,
                work_dir=work,
                keep_work=False,
            )
        )

    if result.output is None:
        raise RuntimeError("Pipeline finished without an output file")
    title = (result.window.title or "").strip() or result.source_title
    mark_done(
        job.id,
        window=result.window.as_dict(),
        output_path=result.output,
        title=title,
        transcript_used=result.transcript_source,
    )


def main() -> None:
    ensure_dirs()
    init_db()
    apply_settings()
    reset = requeue_stale_running()
    if reset:
        print(f"Requeued {reset} job(s) left running after a restart")
    print("Worker waiting for jobs…")
    while True:
        job = claim_next_job()
        if job is None:
            time.sleep(WORKER_POLL_SECONDS)
            continue
        print(f"Running job {job.id} ({job.source_label})")
        try:
            process_job(job)
            print(f"Finished job {job.id}")
        except Exception as exc:
            mark_failed(job.id, str(exc))
            log = log_path(job.id)
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(f"\nerror: {exc}\n")
                handle.write(traceback.format_exc())
            print(f"Job {job.id} failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
