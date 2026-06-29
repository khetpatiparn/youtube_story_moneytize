from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository


@dataclass(frozen=True)
class ApprovalRequest:
    project_id: str
    approved: bool
    reviewer: str
    notes: str = ""


@dataclass(frozen=True)
class ApprovalDecision:
    project_id: str
    stage: str
    approved: bool
    reviewer: str
    notes: str
    decided_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "stage": self.stage,
            "approved": self.approved,
            "reviewer": self.reviewer,
            "notes": self.notes,
            "decided_at": self.decided_at,
        }


@dataclass(frozen=True)
class ReportRequest:
    project_id: str
    video_path: str
    quality_score: float
    issues: list[str]


@dataclass(frozen=True)
class ReportPaths:
    quality_report_path: str
    contact_sheet_path: str
    project_report_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "quality_report_path": self.quality_report_path,
            "contact_sheet_path": self.contact_sheet_path,
            "project_report_path": self.project_report_path,
        }


class ApprovalReportingService:
    def __init__(
        self,
        repository: ProjectRepository,
        checkpoints: CheckpointRepository | None = None,
    ):
        self.repository = repository
        self.checkpoints = checkpoints

    def record_script_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        checkpoint = self._validate_checkpoint_gate(request.project_id, "script")
        decision = self._record_approval("script", request)
        if checkpoint is not None:
            self._reconcile_checkpoint(request.project_id, checkpoint.state)
            return decision
        metadata = self.repository.load_project(request.project_id).with_status(
            "script_approved" if request.approved else "script_changes_requested",
            current_node="script_approval",
        )
        self.repository.save_project(metadata)
        return decision

    def record_final_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        checkpoint = self._validate_checkpoint_gate(request.project_id, "final")
        decision = self._record_approval("final", request)
        if checkpoint is not None:
            self._reconcile_checkpoint(request.project_id, checkpoint.state)
            return decision
        metadata = self.repository.load_project(request.project_id).with_status(
            "final_approved" if request.approved else "final_changes_requested",
            current_node="final_approval",
        )
        self.repository.save_project(metadata)
        return decision

    def _validate_checkpoint_gate(self, project_id: str, stage: str):
        if self.checkpoints is None:
            return None
        checkpoint = self.checkpoints.load_latest(project_id)
        if checkpoint is None:
            return None
        from app.services.pipeline_runner import approval_stage_is_eligible

        if not approval_stage_is_eligible(checkpoint.state, stage):
            raise ValueError(f"{stage} approval is only allowed at the {stage} approval gate")
        return checkpoint

    def _reconcile_checkpoint(self, project_id: str, state) -> None:
        from app.services.pipeline_runner import PipelineRunner

        assert self.checkpoints is not None
        PipelineRunner(self.repository, self.checkpoints).reconcile_approval_only(
            project_id, state
        )

    def write_project_reports(self, request: ReportRequest) -> ReportPaths:
        if not 0 <= request.quality_score <= 1:
            raise ValueError("quality_score must be between 0 and 1")

        project_dir = self.repository.project_dir(request.project_id)
        reports_dir = project_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        metadata = self.repository.load_project(request.project_id)
        approvals = self._load_approvals(project_dir)
        scenes = self._load_scenes(project_dir)
        generated_at = _timestamp()

        quality_report = {
            "project_id": request.project_id,
            "video_path": _safe_relative_path(request.video_path, "video_path"),
            "quality_score": request.quality_score,
            "issues": request.issues,
            "generated_at": generated_at,
        }
        (reports_dir / "quality_report.json").write_text(
            json.dumps(quality_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        (reports_dir / "contact_sheet.md").write_text(
            self._render_contact_sheet(request.project_id, scenes),
            encoding="utf-8",
        )
        (reports_dir / "project_report.md").write_text(
            self._render_project_report(
                project_id=request.project_id,
                topic=metadata.topic,
                status=metadata.status,
                approvals=approvals,
                quality_report=quality_report,
                scenes=scenes,
            ),
            encoding="utf-8",
        )

        return ReportPaths(
            quality_report_path="reports/quality_report.json",
            contact_sheet_path="reports/contact_sheet.md",
            project_report_path="reports/project_report.md",
        )

    def _record_approval(self, stage: str, request: ApprovalRequest) -> ApprovalDecision:
        reviewer = request.reviewer.strip()
        if not reviewer:
            raise ValueError("reviewer is required")

        project_dir = self.repository.project_dir(request.project_id)
        reports_dir = project_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        approvals = self._load_approvals(project_dir)
        decision = ApprovalDecision(
            project_id=request.project_id,
            stage=stage,
            approved=request.approved,
            reviewer=reviewer,
            notes=request.notes.strip(),
            decided_at=_timestamp(),
        )
        approvals[stage] = decision.to_dict()
        (reports_dir / "approvals.json").write_text(
            json.dumps(approvals, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return decision

    def _load_approvals(self, project_dir: Path) -> dict[str, object]:
        approvals_path = project_dir / "reports" / "approvals.json"
        if not approvals_path.exists():
            return {}
        with approvals_path.open(encoding="utf-8") as file:
            return json.load(file)

    def _load_scenes(self, project_dir: Path) -> list[dict[str, object]]:
        scenes_path = project_dir / "scenes" / "scenes.json"
        if not scenes_path.exists():
            return []
        with scenes_path.open(encoding="utf-8") as file:
            scenes = json.load(file)
        if not isinstance(scenes, list):
            raise ValueError("scenes/scenes.json must contain a list")
        return scenes

    def _render_contact_sheet(self, project_id: str, scenes: list[dict[str, object]]) -> str:
        lines = [f"# Contact Sheet: {project_id}", ""]
        if not scenes:
            lines.extend(["No scenes are available yet.", ""])
            return "\n".join(lines)

        for index, scene in enumerate(scenes, start=1):
            scene_id = str(scene.get("scene_id") or scene.get("sceneId") or f"scene_{index:03d}")
            image_path = str(scene.get("image_path") or scene.get("imagePath") or "")
            prompt = str(scene.get("prompt") or "")
            lines.extend(
                [
                    f"## {index}. {scene_id}",
                    f"- Image: {image_path or 'missing'}",
                    f"- Prompt: {prompt or 'missing'}",
                    "",
                ]
            )
        return "\n".join(lines)

    def _render_project_report(
        self,
        project_id: str,
        topic: str,
        status: str,
        approvals: dict[str, object],
        quality_report: dict[str, object],
        scenes: list[dict[str, object]],
    ) -> str:
        script_status = _approval_label(approvals.get("script"))
        final_status = _approval_label(approvals.get("final"))
        issues = quality_report["issues"]
        issue_lines = "\n".join(f"- {issue}" for issue in issues) if issues else "- None"
        return "\n".join(
            [
                f"# Project Report: {project_id}",
                "",
                f"- Topic: {topic}",
                f"- Status: {status}",
                f"- Scene count: {len(scenes)}",
                f"- Video path: {quality_report['video_path']}",
                f"- Quality score: {quality_report['quality_score']}",
                f"- Script approval: {script_status}",
                f"- Final approval: {final_status}",
                "",
                "## Quality Issues",
                issue_lines,
                "",
            ]
        )


def _approval_label(value: object) -> str:
    if not isinstance(value, dict):
        return "pending"
    return "approved" if value.get("approved") is True else "changes requested"


def _safe_relative_path(value: str, name: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must be a relative path inside the project")
    return value.replace("\\", "/")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
