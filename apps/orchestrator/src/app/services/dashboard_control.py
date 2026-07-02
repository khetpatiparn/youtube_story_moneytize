from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.repositories.checkpoint_repository import CheckpointRecord, CheckpointRepository
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import CreateProjectRequest, ProjectMetadata
from app.schemas.job import JobRecord
from app.services.approval_reporting import ApprovalReportingService, ApprovalRequest
from app.services.job_worker import JobWorker
from app.services.pipeline_runner import PipelineRunner, approval_stage_is_eligible

CREATE_FIELDS = {"topic", "duration", "profile", "targetLanguage", "projectId"}
COPY_DIRECTORIES = ("input", "research", "outline", "script", "scenes", "prompts", "thumbnail")


def _read_optional_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _available_relative_path(project_dir: Path, relative_path: tuple[str, ...]) -> str | None:
    target = project_dir.joinpath(*relative_path)
    return "/".join(relative_path) if target.exists() else None


def _normalize_scene(scene: dict[str, Any]) -> dict[str, Any]:
    return {
        "sceneId": scene.get("sceneId") or scene.get("scene_id"),
        "imagePath": scene.get("imagePath") or scene.get("image_path"),
        "prompt": scene.get("prompt") or "",
    }


def _normalize_approval(entry: object) -> str:
    if not isinstance(entry, dict):
        return "pending"
    if entry.get("approved") is True:
        return "approved"
    if entry.get("approved") is False:
        return "changes_requested"
    return "pending"


def _normalize_quality(report: object) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"score": None, "issues": [], "videoPath": None}
    issues = report.get("issues")
    return {
        "score": report.get("quality_score")
        if isinstance(report.get("quality_score"), (int, float))
        else report.get("score"),
        "issues": list(issues) if isinstance(issues, list) else [],
        "videoPath": report.get("video_path") or report.get("videoPath"),
    }


def available_actions(
    metadata: ProjectMetadata,
    checkpoint: CheckpointRecord | None,
) -> list[str]:
    if checkpoint is None and metadata.status == "created":
        return ["run"]
    if checkpoint is None:
        return []

    actions: list[str] = []
    if metadata.status in {
        "script_changes_requested",
        "image_generation_failed",
        "quality_validation_failed",
        "awaiting_final_approval",
        "final_changes_requested",
        "script_approved",
        "awaiting_script_approval",
    }:
        actions.append("resume")
    if approval_stage_is_eligible(checkpoint.state, "script"):
        actions.append("approve_script")
    if approval_stage_is_eligible(checkpoint.state, "final"):
        actions.append("approve_final")
    return actions


class DashboardControlService:
    def __init__(
        self,
        projects: ProjectRepository,
        checkpoints: CheckpointRepository,
    ) -> None:
        self.projects = projects
        self.checkpoints = checkpoints

    def list_projects(self) -> list[dict[str, object]]:
        if not self.projects.projects_dir.exists():
            return []
        projects: list[dict[str, object]] = []
        for entry in sorted(self.projects.projects_dir.iterdir(), key=lambda path: path.name):
            if not entry.is_dir():
                continue
            try:
                projects.append(self.get_project(entry.name))
            except FileNotFoundError:
                continue
        return projects

    def get_project(self, project_id: str) -> dict[str, object]:
        project_dir = self.projects.project_dir(project_id)
        try:
            metadata = self.projects.load_project(project_id)
        except FileNotFoundError as error:
            raise KeyError(project_id) from error
        checkpoint = self.checkpoints.load_latest(project_id)
        return build_project_summary(metadata, checkpoint, project_dir)

    def create_project(self, payload: dict[str, object]) -> dict[str, object]:
        unknown = set(payload) - CREATE_FIELDS
        if unknown:
            raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")

        topic = payload.get("topic", "")
        duration = payload.get("duration")
        profile = payload.get("profile", "")
        target_language = payload.get("targetLanguage", "th")
        project_id = payload.get("projectId")

        if not isinstance(topic, str) or len(topic.strip()) > 500:
            raise ValueError("topic must be a non-empty string up to 500 characters")
        if isinstance(duration, bool) or not isinstance(duration, int) or not 15 <= duration <= 3600:
            raise ValueError("duration must be an integer between 15 and 3600")
        if not isinstance(profile, str) or not profile.strip() or len(profile.strip()) > 64:
            raise ValueError("profile must be a non-empty string up to 64 characters")
        if not isinstance(target_language, str) or not target_language.strip() or len(target_language.strip()) > 16:
            raise ValueError("targetLanguage must be a non-empty string up to 16 characters")
        if project_id is not None and (not isinstance(project_id, str) or not project_id.strip()):
            raise ValueError("projectId must be a non-empty string when provided")

        request = CreateProjectRequest(
            topic=topic,
            duration=duration,
            profile=profile,
            target_language=target_language,
        )
        metadata = self.projects.create_project(request, project_id=project_id)
        return build_project_summary(metadata, None, self.projects.project_dir(metadata.project_id))

    def copy_project(self, project_id: str) -> dict[str, object]:
        metadata = self.projects.load_project(project_id)
        source_dir = self.projects.project_dir(project_id)
        copied = self.projects.create_project(
            CreateProjectRequest(
                topic=metadata.topic,
                duration=metadata.target_duration_seconds,
                profile=metadata.channel_style_profile,
                target_language=metadata.target_language,
            )
        )
        copied_dir = self.projects.project_dir(copied.project_id)
        for name in COPY_DIRECTORIES:
            source = source_dir / name
            target = copied_dir / name
            if not source.exists():
                continue
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(source, target)
        return build_project_summary(copied, None, copied_dir)

    def delete_project(self, project_id: str, *, confirm_project_id: str) -> dict[str, object]:
        if confirm_project_id != project_id:
            raise ValueError("confirmProjectId must exactly match the project id")
        checkpoint = self.checkpoints.load_latest(project_id)
        if checkpoint is not None and checkpoint.state.get("job_status") == "running":
            raise ValueError("project has an active job")
        project_dir = self.projects.project_dir(project_id)
        if not project_dir.exists():
            raise KeyError(project_id)
        trash_root = self.projects.projects_dir / ".trash"
        trash_root.mkdir(parents=True, exist_ok=True)
        trash_dir = trash_root / project_id
        if trash_dir.exists():
            shutil.rmtree(trash_dir, ignore_errors=True)
        project_dir.replace(trash_dir)
        shutil.rmtree(trash_dir, ignore_errors=True)
        return {"ok": True, "projectId": project_id}


def build_project_summary(
    metadata: ProjectMetadata,
    checkpoint: CheckpointRecord | None,
    project_dir: Path,
) -> dict[str, object]:
    state = checkpoint.state if checkpoint is not None else {}
    scenes_data = _read_optional_json(project_dir / "scenes" / "scenes.json", [])
    approvals_data = _read_optional_json(project_dir / "reports" / "approvals.json", {})
    quality_data = _read_optional_json(project_dir / "reports" / "quality_report.json", {})
    scenes = [
        _normalize_scene(scene)
        for scene in scenes_data
        if isinstance(scene, dict)
    ] if isinstance(scenes_data, list) else []

    return {
        "projectId": metadata.project_id,
        "topic": metadata.topic,
        "status": metadata.status,
        "currentNode": state.get("current_node"),
        "waitingFor": state.get("waiting_for"),
        "targetDurationSeconds": metadata.target_duration_seconds,
        "targetLanguage": metadata.target_language,
        "source": "live",
        "availableActions": available_actions(metadata, checkpoint),
        "scenes": scenes,
        "approvals": {
            "script": _normalize_approval(approvals_data.get("script")),
            "final": _normalize_approval(approvals_data.get("final")),
        },
        "quality": _normalize_quality(quality_data),
        "reports": {
            "contactSheetPath": _available_relative_path(project_dir, ("reports", "contact_sheet.md")),
            "projectReportPath": _available_relative_path(project_dir, ("reports", "project_report.md")),
            "qualityReportPath": _available_relative_path(project_dir, ("reports", "quality_report.json")),
        },
    }


class DashboardActionAdapter:
    def __init__(
        self,
        projects: ProjectRepository,
        checkpoints: CheckpointRepository,
        *,
        runner_factory: Callable[..., Any] | None = None,
        approval_service_factory: Callable[[], ApprovalReportingService] | None = None,
        summary_service: DashboardControlService | None = None,
    ) -> None:
        self.projects = projects
        self.checkpoints = checkpoints
        self.runner_factory = runner_factory
        self.approval_service_factory = approval_service_factory or self._default_approval_service_factory
        self.summary_service = summary_service or DashboardControlService(projects, checkpoints)

    def run_project(self, project_id: str, *, progress_reporter: Any = None) -> dict[str, object]:
        self.projects.project_dir(project_id)
        if self.runner_factory is None:
            raise ValueError("runner_factory is required for run")
        result = self.runner_factory(
            project_id,
            configure_content=True,
            progress_reporter=progress_reporter,
        ).run(project_id)
        return self._action_summary(
            project_id,
            "run",
            "Project started successfully.",
            result,
        )

    def resume_project(self, project_id: str, *, progress_reporter: Any = None) -> dict[str, object]:
        self.projects.project_dir(project_id)
        if self.runner_factory is None:
            raise ValueError("runner_factory is required for resume")
        result = self.runner_factory(
            project_id,
            configure_content=False,
            progress_reporter=progress_reporter,
        ).resume(project_id)
        return self._action_summary(
            project_id,
            "resume",
            "Project resumed successfully.",
            result,
        )

    def approve(self, stage: str, project_id: str, approved: bool, reviewer: str | None) -> dict[str, object]:
        self.projects.project_dir(project_id)
        if stage not in {"script", "final"}:
            raise ValueError("approval stage must be 'script' or 'final'")
        if not isinstance(approved, bool):
            raise ValueError("approved must be a boolean")
        normalized_reviewer = (reviewer or "human").strip() or "human"
        if len(normalized_reviewer) > 64:
            raise ValueError("reviewer must be at most 64 characters")
        service = self.approval_service_factory()
        request = ApprovalRequest(
            project_id=project_id,
            approved=approved,
            reviewer=normalized_reviewer,
        )
        if stage == "script":
            service.record_script_approval(request)
        else:
            service.record_final_approval(request)
        message = (
            "Script approval recorded."
            if stage == "script"
            else "Final approval recorded."
        )
        return self._action_summary(project_id, f"approve_{stage}", message)

    def _action_summary(
        self,
        project_id: str,
        action: str,
        message: str,
        state: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        if state is None:
            refreshed = self.summary_service.get_project(project_id)
            status = refreshed["status"]
            current_node = refreshed["currentNode"]
        else:
            status = state.get("status")
            current_node = state.get("current_node")
        return {
            "ok": True,
            "projectId": project_id,
            "action": action,
            "status": status,
            "currentNode": current_node,
            "message": message,
        }

    def _default_approval_service_factory(self) -> ApprovalReportingService:
        return ApprovalReportingService(self.projects, self.checkpoints)


class DashboardJobService:
    def __init__(self, jobs: JobRepository, worker: JobWorker) -> None:
        self.jobs = jobs
        self.worker = worker

    def enqueue(self, project_id: str, operation: str) -> dict[str, object]:
        job = self.jobs.enqueue(project_id, operation)
        return _job_to_dict(job)

    def list_jobs(self, project_id: str | None = None) -> list[dict[str, object]]:
        return [_job_to_dict(job) for job in self.jobs.list_jobs(project_id)]

    def get_job(self, job_id: str) -> dict[str, object]:
        return _job_to_dict(self.jobs.get(job_id))

    def cancel_job(self, job_id: str) -> dict[str, object]:
        return _job_to_dict(self.jobs.request_cancel(job_id))


def _job_to_dict(job: JobRecord) -> dict[str, object]:
    return {
        "jobId": job.job_id,
        "projectId": job.project_id,
        "operation": job.operation,
        "status": job.status,
        "sceneId": job.scene_id,
        "progress": job.progress,
        "stage": job.stage,
        "previewImagePath": job.preview_image_path,
        "scriptExcerpt": job.script_excerpt,
        "promptExcerpt": job.prompt_excerpt,
        "attempts": job.attempts,
        "errorCode": job.error_code,
        "errorMessage": job.error_message,
        "cancelRequested": job.cancel_requested,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
    }
