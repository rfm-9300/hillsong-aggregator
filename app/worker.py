from __future__ import annotations

import shutil
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from app.assets import active_package_paths
from app.config import OUTPUTS_DIR, WORK_DIR, WORKER_POLL_SECONDS, ensure_dirs
from app.settings import apply as apply_settings
from app.jobs import (
    claim_next_job,
    init_db,
    log_path,
    mark_done,
    mark_failed,
    recover_stale_running,
)
from app.watch import init_watch_db, start_monitor
from sermon_cut.media import package_sermon
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
    sermon_out = OUTPUTS_DIR / f"{job.id}_sermon.mp4"
    final_out = OUTPUTS_DIR / f"{job.id}.mp4"
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
                output=sermon_out,
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

        intro, outro, package_meta = active_package_paths()
        output = final_out
        package = None
        if intro or outro:
            labels = []
            if intro:
                labels.append(f"intro={package_meta.get('intro_title') or intro.name}")
            if outro:
                labels.append(f"ending={package_meta.get('outro_title') or outro.name}")
            print(f"Packaging final video ({', '.join(labels)})…")
            try:
                package_sermon(result.output, final_out, intro=intro, outro=outro)
                print(f"Wrote packaged video {final_out}")
                package = package_meta
            except Exception as package_exc:
                print(f"Packaging failed: {package_exc}")
                print("Keeping the sermon cut as the final video.")
                if result.output.resolve() != final_out.resolve():
                    shutil.copy2(result.output, final_out)
                package = None
        else:
            print("No intro/ending selected on Edit; using sermon cut as final video.")
            if result.output.resolve() != final_out.resolve():
                shutil.copy2(result.output, final_out)

    title = (result.window.title or "").strip() or result.source_title
    mark_done(
        job.id,
        window=result.window.as_dict(),
        output_path=output,
        sermon_path=result.output,
        title=title,
        transcript_used=result.transcript_source,
        package=package,
    )


def main() -> None:
    ensure_dirs()
    init_db()
    init_watch_db()
    apply_settings()
    start_monitor()
    requeued, interrupted = recover_stale_running()
    if requeued:
        print(f"Requeued {requeued} job(s) left running after a restart")
    if interrupted:
        print(
            f"Marked {interrupted} job(s) interrupted during packaging "
            "(sermon cut kept — use Rebuild on the job page)"
        )
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
