from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.repositories.checkpoint_repository import CheckpointRecord, CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectMetadata
from app.services.approval_reporting import ApprovalReportingService, ApprovalRequest
from app.services.pipeline_runner import PipelineRunner, approval_stage_is_eligible


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
        runner_factory: Callable[[str, bool], Any] | None = None,
        approval_service_factory: Callable[[], ApprovalReportingService] | None = None,
        summary_service: DashboardControlService | None = None,
    ) -> None:
        self.projects = projects
        self.checkpoints = checkpoints
        self.runner_factory = runner_factory
        self.approval_service_factory = approval_service_factory or self._default_approval_service_factory
        self.summary_service = summary_service or DashboardControlService(projects, checkpoints)

    def run_project(self, project_id: str) -> dict[str, object]:
        self.projects.project_dir(project_id)
        if self.runner_factory is None:
            raise ValueError("runner_factory is required for run")
        result = self.runner_factory(project_id, configure_content=True).run(project_id)
        return self._action_summary(
            project_id,
            "run",
            "Project started successfully.",
            result,
        )

    def resume_project(self, project_id: str) -> dict[str, object]:
        self.projects.project_dir(project_id)
        if self.runner_factory is None:
            raise ValueError("runner_factory is required for resume")
        result = self.runner_factory(project_id, configure_content=False).resume(project_id)
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
