from __future__ import annotations

import json
from typing import Any

from app.providers.local import LocalImageProvider, LocalTTSProvider
from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.state import VideoProjectState
from app.services.artifacts import ArtifactStore
from app.services.content_pipeline import ContentPipeline
from app.services.image_pipeline import ImageGenerationExhausted, ImagePipeline
from app.services.timeline import build_timeline, wav_duration_seconds


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
        image_error: ImageGenerationExhausted | None = None
        if state.get("script_approved") is True and state.get("current_node") == "script_approval":
            store = ArtifactStore(self.projects.project_dir(project_id))
            provider = self.image_provider or LocalImageProvider(store)
            try:
                images = ImagePipeline(store, provider).generate(
                    state["scenes"], existing_jobs=state.get("image_jobs")
                )
            except ImageGenerationExhausted as error:
                images = error.result
                image_error = error
            state.update(images)
            state["current_node"] = "images"
            state["status"] = "image_generation_failed" if image_error else "media_ready"
        if state.get("status") in {"media_ready", "render_ready"} and state.get("current_node") in {
            "images",
            "render",
        }:
            state = self._reconcile_audio_timeline(project_id, state)
        current_metadata = self.projects.load_project(project_id)
        metadata = current_metadata.with_graph_result(state)
        if metadata != current_metadata:
            self.projects.save_project(metadata)
        latest = self.checkpoints.load_latest(project_id)
        if latest is None or latest.state != state:
            self.checkpoints.save_checkpoint(project_id, state)
        if image_error is not None:
            raise image_error
        return state

    def _reconcile_audio_timeline(
        self, project_id: str, state: VideoProjectState
    ) -> VideoProjectState:
        store = ArtifactStore(self.projects.project_dir(project_id))
        audio_relative = "audio/narration.wav"
        audio_path = store.path(audio_relative)
        try:
            duration = wav_duration_seconds(audio_path)
        except ValueError:
            provider = self.tts_provider or LocalTTSProvider(store)
            result = provider.synthesize_sync(
                state["script"], "narrator-th", audio_relative, {"words_per_second": 2.5}
            )
            duration = wav_duration_seconds(store.path(result.output_path))

        timeline = build_timeline(state["scenes"], duration, fps=30)
        payload = {
            "fps": 30,
            "width": 1280,
            "height": 720,
            "audioPath": audio_relative,
            "scenes": [
                {
                    "sceneId": scene["scene_id"],
                    "startFrame": timing["start_frame"],
                    "durationInFrames": timing["duration_in_frames"],
                    "imagePath": image["output_path"],
                    "motion": scene.get("motion", "slow_push"),
                    "focalPoint": scene.get("focal_point", [0.5, 0.5]),
                }
                for scene, timing, image in zip(
                    state["scenes"], timeline, state["generated_images"]
                )
            ],
        }
        payload_relative = "render/render_payload.json"
        if not self._payload_matches(store, payload_relative, payload):
            store.write_json(payload_relative, payload)
        state.update(
            {
                "voice_provider": getattr(self.tts_provider, "provider", "local"),
                "voice_path": audio_relative,
                "audio_duration_seconds": duration,
                "timeline": timeline,
                "render_payload_path": payload_relative,
                "status": "render_ready",
                "current_node": "render",
            }
        )
        return state

    @staticmethod
    def _payload_matches(store: ArtifactStore, path: str, expected: dict[str, Any]) -> bool:
        try:
            return store.read_json(path) == expected
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False

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
        if (
            stage == "script"
            and approved
            and state.get("current_node") in {"images", "render"}
            and state.get("status") in {"media_ready", "render_ready"}
        ):
            return state
        state[f"{stage}_approved"] = approved
        state["status"] = f"{stage}_approved" if approved else f"{stage}_changes_requested"
        state["current_node"] = f"{stage}_approval"
        if approved:
            state.pop("waiting_for", None)
        else:
            state["waiting_for"] = stage
        return state


def _approval_stage_for_state(state: VideoProjectState) -> str | None:
    current_node = state.get("current_node")
    status = state.get("status", "")
    if (
        current_node == "script_approval"
        and status in {"awaiting_script_approval", "script_approved", "script_changes_requested"}
    ) or (current_node == "images" and status in {"media_ready", "image_generation_failed"}) or (
        current_node == "render" and status == "render_ready"
    ):
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
