from __future__ import annotations

from app.repositories.job_repository import JobRepository


class ProgressReporter:
    def __init__(self, jobs: JobRepository, job_id: str) -> None:
        self.jobs = jobs
        self.job_id = job_id

    def stage(self, name: str, progress: float) -> None:
        self.jobs.update_progress(self.job_id, progress=progress, stage=name)

    def scene(
        self,
        scene_id: str,
        status: str,
        *,
        attempt: int,
        progress: float,
        error: str | None = None,
    ) -> None:
        del attempt
        del error
        self.jobs.update_progress(
            self.job_id,
            progress=progress,
            stage=f"scene:{scene_id}:{status}",
        )
