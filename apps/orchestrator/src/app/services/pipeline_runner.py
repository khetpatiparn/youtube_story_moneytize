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
        self.projects.load_project(project_id)
        existing = self.checkpoints.load_latest(project_id)
        if existing is not None:
            return dict(existing.state)

        metadata = self.projects.load_project(project_id)
        pipeline = ContentPipeline(ArtifactStore(self.projects.project_dir(project_id)))
        state = pipeline.generate(metadata.to_graph_state())
        paused: VideoProjectState = {
            **state,
            "status": "awaiting_script_approval",
            "current_node": "script_approval",
            "waiting_for": "script",
        }
        self.checkpoints.save_checkpoint(project_id, paused)
        self.projects.save_project(metadata.with_graph_result(paused))
        return paused

    def resume(self, project_id: str) -> VideoProjectState:
        self.projects.load_project(project_id)
        checkpoint = self.checkpoints.load_latest(project_id)
        if checkpoint is None:
            raise ValueError(f"No checkpoint found for project_id {project_id}")

        state = dict(checkpoint.state)
        approvals_path = self.projects.project_dir(project_id) / "reports" / "approvals.json"
        if not approvals_path.exists():
            return state
        with approvals_path.open(encoding="utf-8") as file:
            approvals = json.load(file)
        if not isinstance(approvals, dict) or not isinstance(approvals.get("script"), dict):
            return state
        if approvals["script"].get("approved") is not True:
            return state
        return state
