from __future__ import annotations

import json
from typing import Any

from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.state import VideoProjectState
from app.services.artifacts import ArtifactStore
from app.services.content_pipeline import ContentPipeline


class PipelineRunner:
    def __init__(
        self,
        projects: ProjectRepository,
        checkpoints: CheckpointRepository,
        *,
        image_provider: Any = None,
        tts_provider: Any = None,
        renderer: Any = None,
    ) -> None:
        self.projects = projects
        self.checkpoints = checkpoints
        self.image_provider = image_provider
        self.tts_provider = tts_provider
        self.renderer = renderer

    def run(self, project_id: str) -> VideoProjectState:
        metadata = self.projects.load_project(project_id)
        existing = self.checkpoints.load_latest(project_id)
        if existing is not None:
            return self.reconcile_state(project_id, existing.state)

        pipeline = ContentPipeline(ArtifactStore(self.projects.project_dir(project_id)))
        state = pipeline.generate(metadata.to_graph_state())
        paused: VideoProjectState = {
            **state,
            "status": "awaiting_script_approval",
            "current_node": "script_approval",
            "waiting_for": "script",
        }
        return self.reconcile_state(project_id, paused)

    def resume(self, project_id: str) -> VideoProjectState:
        self.projects.load_project(project_id)
        checkpoint = self.checkpoints.load_latest(project_id)
        if checkpoint is None:
            raise ValueError(f"No checkpoint found for project_id {project_id}")

        return self.reconcile_state(project_id, checkpoint.state)

    def reconcile_state(
        self,
        project_id: str,
        checkpoint_state: VideoProjectState,
    ) -> VideoProjectState:
        state = self._apply_durable_approval(project_id, dict(checkpoint_state))
        current_metadata = self.projects.load_project(project_id)
        metadata = current_metadata.with_graph_result(state)
        if metadata != current_metadata:
            self.projects.save_project(metadata)
        latest = self.checkpoints.load_latest(project_id)
        if latest is None or latest.state != state:
            self.checkpoints.save_checkpoint(project_id, state)
        return state

    def _apply_durable_approval(
        self,
        project_id: str,
        state: VideoProjectState,
    ) -> VideoProjectState:
        approvals_path = self.projects.project_dir(project_id) / "reports" / "approvals.json"
        if not approvals_path.exists():
            return state
        with approvals_path.open(encoding="utf-8") as file:
            approvals = json.load(file)
        if not isinstance(approvals, dict):
            raise ValueError("reports/approvals.json must contain an object")
        stage = _approval_stage_for_state(state)
        if stage is None or not isinstance(approvals.get(stage), dict):
            return state
        approved = approvals[stage].get("approved") is True
        state[f"{stage}_approved"] = approved
        state["status"] = f"{stage}_approved" if approved else f"{stage}_changes_requested"
        state["current_node"] = f"{stage}_approval"
        if approved:
            state.pop("waiting_for", None)
        return state


def _approval_stage_for_state(state: VideoProjectState) -> str | None:
    current_node = state.get("current_node")
    status = state.get("status", "")
    if current_node == "script_approval" and status in {
        "awaiting_script_approval",
        "script_approved",
        "script_changes_requested",
    }:
        return "script"
    if current_node == "final_approval" and status in {
        "awaiting_final_approval",
        "final_approved",
        "final_changes_requested",
    }:
        return "final"
    return None


def approval_stage_is_eligible(state: VideoProjectState, stage: str) -> bool:
    return _approval_stage_for_state(state) == stage
