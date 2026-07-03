from __future__ import annotations

from app.repositories.job_repository import JobRepository
from app.services.project_events import ProjectEventStore


class JobCancelledError(RuntimeError):
    pass


class ProgressReporter:
    def __init__(self, jobs: JobRepository, job_id: str, events: ProjectEventStore | None = None) -> None:
        self.jobs = jobs
        self.job_id = job_id
        self.events = events

    def _project_id(self) -> str:
        return self.jobs.get(self.job_id).project_id

    def stage(self, name: str, progress: float) -> None:
        self.raise_if_cancelled()
        self.jobs.update_progress(self.job_id, progress=progress, stage=name)
        if self.events is not None:
            self.events.append(self._project_id(), name, None, f"Stage updated to {name}")

    def scene(
        self,
        scene_id: str,
        status: str,
        *,
        attempt: int,
        progress: float,
        prompt_excerpt: str | None = None,
        script_excerpt: str | None = None,
        preview_image_path: str | None = None,
        error: str | None = None,
    ) -> None:
        self.raise_if_cancelled()
        self.jobs.update_progress(
            self.job_id,
            progress=progress,
            stage=status,
            scene_id=scene_id,
            preview_image_path=preview_image_path,
            script_excerpt=script_excerpt,
            prompt_excerpt=prompt_excerpt,
        )
        if self.events is not None:
            message = f"{status} for {scene_id} (attempt {attempt})"
            if error:
                message = f"{message}: {error}"
            self.events.append(
                self._project_id(),
                status,
                scene_id,
                message,
                promptExcerpt=prompt_excerpt,
                scriptExcerpt=script_excerpt,
                previewImagePath=preview_image_path,
            )

    def raise_if_cancelled(self) -> None:
        if self.jobs.get(self.job_id).cancel_requested:
            raise JobCancelledError(f"job {self.job_id} was cancelled")
