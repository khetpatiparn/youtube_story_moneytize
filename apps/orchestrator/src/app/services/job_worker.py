from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.repositories.job_repository import JobRepository
from app.services.error_sanitizer import sanitize_error
from app.services.project_events import ProjectEventStore
from app.services.progress_reporter import JobCancelledError, ProgressReporter

OPERATIONS = {"run": "run_project", "resume": "resume_project"}


class JobWorker:
    def __init__(
        self,
        jobs: JobRepository,
        actions: Any,
        *,
        events: ProjectEventStore | None = None,
        secret_values: Callable[[], list[str]] | None = None,
    ) -> None:
        self.jobs = jobs
        self.actions = actions
        self.events = events
        self.secret_values = secret_values or (lambda: [])

    def process_one(self) -> bool:
        job = self.jobs.claim_next()
        if job is None:
            return False

        try:
            reporter = ProgressReporter(self.jobs, job.job_id, self.events)
            result = getattr(self.actions, OPERATIONS[job.operation])(
                job.project_id,
                progress_reporter=reporter,
            )
            reporter.raise_if_cancelled()
            self.jobs.finish(
                job.job_id,
                "succeeded",
                progress=1.0,
                stage=result.get("currentNode"),
            )
        except JobCancelledError:
            self.jobs.finish(job.job_id, "cancelled")
        except Exception as error:
            code, message = sanitize_error(error, self.secret_values())
            self.jobs.finish(
                job.job_id,
                "failed",
                error_code=code,
                error_message=message,
            )
        return True

    def recover_interrupted_jobs(self) -> list[object]:
        return self.jobs.reopen_interrupted_jobs()
