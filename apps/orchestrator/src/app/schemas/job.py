from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    project_id: str
    operation: str
    status: str
    scene_id: str | None
    progress: float
    stage: str | None
    preview_image_path: str | None
    script_excerpt: str | None
    prompt_excerpt: str | None
    attempts: int
    error_code: str | None
    error_message: str | None
    cancel_requested: bool
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
