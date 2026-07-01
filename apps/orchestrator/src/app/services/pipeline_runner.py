from __future__ import annotations

import asyncio
import hashlib
import json
import math
from typing import Any

from app.providers.base import AudioResult
from app.providers.local import LocalImageProvider, LocalTTSProvider
from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.state import VideoProjectState
from app.services.artifacts import ArtifactStore
from app.services.content_pipeline import ContentPipeline
from app.services.image_pipeline import ImageGenerationExhausted, ImagePipeline
from app.services.approval_reporting import ApprovalReportingService, ReportRequest
from app.services.quality import QualityResult, quality_input_fingerprint, validate_project_media
from app.services.timeline import build_timeline, wav_duration_seconds


class PipelineRunner:
    def __init__(
        self,
        projects: ProjectRepository,
        checkpoints: CheckpointRepository,
        *,
        content_provider: Any = None,
        image_provider: Any = None,
        tts_provider: Any = None,
        renderer: Any = None,
        video_probe: Any = None,
        max_image_attempts: int = 3,
        tts_words_per_second: float = 2.5,
    ) -> None:
        self.projects = projects
        self.checkpoints = checkpoints
        self.content_provider = content_provider
        self.image_provider = image_provider
        self.tts_provider = tts_provider
        self.renderer = renderer
        self.video_probe = video_probe
        if (
            isinstance(max_image_attempts, bool)
            or not isinstance(max_image_attempts, int)
            or max_image_attempts <= 0
        ):
            raise ValueError("max_image_attempts must be a positive integer")
        self.max_image_attempts = max_image_attempts
        if not isinstance(tts_words_per_second, (int, float)) or not math.isfinite(
            tts_words_per_second
        ) or tts_words_per_second <= 0:
            raise ValueError("tts_words_per_second must be finite and positive")
        self.tts_words_per_second = float(tts_words_per_second)

    def run(self, project_id: str) -> VideoProjectState:
        metadata = self.projects.load_project(project_id)
        existing = self.checkpoints.load_latest(project_id)
        if existing is not None:
            return self.reconcile_state(project_id, existing.state)

        pipeline = ContentPipeline(
            ArtifactStore(self.projects.project_dir(project_id)),
            self.content_provider,
        )
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
        if state.get("status") == "final_approved" and state.get("current_node") == "final_approval":
            state.update({"status": "completed", "current_node": "complete"})
            state.pop("waiting_for", None)
        image_error: ImageGenerationExhausted | None = None
        if state.get("script_approved") is True and state.get("current_node") == "script_approval":
            store = ArtifactStore(self.projects.project_dir(project_id))
            provider = self.image_provider or LocalImageProvider(store)
            try:
                images = ImagePipeline(
                    store, provider, max_attempts=self.max_image_attempts
                ).generate(
                    state["scenes"], existing_jobs=state.get("image_jobs")
                )
            except ImageGenerationExhausted as error:
                images = error.result
                image_error = error
            state.update(images)
            state["current_node"] = "images"
            state["status"] = "image_generation_failed" if image_error else "media_ready"
        if (
            state.get("status") == "media_ready" and state.get("current_node") == "images"
        ) or (
            self.renderer is None
            and state.get("status") == "render_ready"
            and state.get("current_node") == "render"
        ):
            state = self._reconcile_audio_timeline(project_id, state)
        if (
            self.renderer is not None
            and state.get("status") == "render_ready"
            and state.get("current_node") == "render"
        ):
            video_path = self.renderer.render(state["render_payload_path"])
            state.update(
                {"video_path": video_path, "status": "rendered", "current_node": "quality"}
            )
        if state.get("status") == "rendered" and state.get("current_node") == "quality":
            project_dir = self.projects.project_dir(project_id)
            store = ArtifactStore(project_dir)
            fingerprint = quality_input_fingerprint(project_dir, state)
            cached = self._load_quality_cache(store, fingerprint)
            if cached is None:
                result = validate_project_media(
                    project_dir,
                    state.get("scenes"),
                    state.get("timeline"),
                    state.get("voice_path"),
                    state.get("video_path"),
                    state.get("render_payload_path"),
                    self.video_probe,
                    generated_images=state.get("generated_images"),
                )
                report_paths = ApprovalReportingService(self.projects).write_project_reports(
                    ReportRequest(
                        project_id=project_id,
                        video_path=state["video_path"],
                        quality_score=result.score,
                        issues=result.issues,
                    )
                ).to_dict()
                self._write_quality_cache(store, fingerprint, result, report_paths)
            else:
                result, report_paths = cached
            quality_report = result.to_dict()
            quality_report.update(report_paths)
            state["quality_report"] = quality_report
            if result.reviewable:
                state.update(
                    {"status": "awaiting_final_approval", "current_node": "final_approval", "waiting_for": "final"}
                )
            else:
                state.update({"status": "quality_validation_failed", "current_node": "quality"})
        self._persist_state(project_id, state)
        if image_error is not None:
            raise image_error
        return state

    def reconcile_approval_only(
        self, project_id: str, checkpoint_state: VideoProjectState
    ) -> VideoProjectState:
        state = self._apply_durable_approval(project_id, dict(checkpoint_state))
        self._persist_state(project_id, state)
        return state

    def _persist_state(self, project_id: str, state: VideoProjectState) -> None:
        current_metadata = self.projects.load_project(project_id)
        metadata = current_metadata.with_graph_result(state)
        if metadata != current_metadata:
            self.projects.save_project(metadata)
        latest = self.checkpoints.load_latest(project_id)
        if latest is None or latest.state != state:
            self.checkpoints.save_checkpoint(project_id, state)

    @staticmethod
    def _load_quality_cache(
        store: ArtifactStore, fingerprint: str
    ) -> tuple[QualityResult, dict[str, str]] | None:
        try:
            cached = store.read_json("reports/quality_state.json")
            if cached.get("fingerprint") != fingerprint:
                return None
            report_paths = cached["report_paths"]
            report_hashes = cached["report_hashes"]
            if not isinstance(report_paths, dict) or not isinstance(report_hashes, dict):
                return None
            for relative in report_paths.values():
                if not isinstance(relative, str):
                    return None
                content = store.path(relative).read_bytes()
                if hashlib.sha256(content).hexdigest() != report_hashes.get(relative):
                    return None
            return QualityResult.from_dict(cached["result"]), report_paths
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_quality_cache(
        store: ArtifactStore,
        fingerprint: str,
        result: QualityResult,
        report_paths: dict[str, str],
    ) -> None:
        report_hashes = {
            relative: hashlib.sha256(store.path(relative).read_bytes()).hexdigest()
            for relative in report_paths.values()
        }
        store.write_json(
            "reports/quality_state.json",
            {
                "fingerprint": fingerprint,
                "result": result.to_dict(),
                "report_paths": report_paths,
                "report_hashes": report_hashes,
            },
        )

    def _reconcile_audio_timeline(
        self, project_id: str, state: VideoProjectState
    ) -> VideoProjectState:
        store = ArtifactStore(self.projects.project_dir(project_id))
        audio_relative = "audio/narration.wav"
        audio_path = store.path(audio_relative)
        try:
            duration = wav_duration_seconds(audio_path)
        except ValueError:
            self._remove_payload(store)
            provider = self.tts_provider or LocalTTSProvider(store)
            result = self._synthesize(
                provider, state["script"], "narrator-th", audio_relative
            )
            self._validate_audio_result(store, result, audio_relative)
            duration = wav_duration_seconds(store.path(audio_relative))
            if not math.isclose(result.duration_seconds, duration, rel_tol=0, abs_tol=1 / 22050):
                raise ValueError("TTS result duration does not match the generated WAV")

        scenes = state.get("scenes")
        images = state.get("generated_images")
        try:
            scene_ids = self._validate_scene_ids(scenes)
            timeline = build_timeline(scenes, duration, fps=30)
            timings, image_by_scene = self._validate_payload_inputs(
                store, scene_ids, timeline, images
            )
        except ValueError:
            self._remove_payload(store)
            raise
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
                for scene in scenes
                for timing in [timings[scene["scene_id"]]]
                for image in [image_by_scene[scene["scene_id"]]]
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

    def _synthesize(
        self, provider: Any, text: str, voice_id: str, output_path: str
    ) -> AudioResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("PipelineRunner cannot synthesize TTS inside a running event loop")
        result = asyncio.run(
            provider.synthesize(
                text,
                voice_id,
                output_path,
                {"words_per_second": self.tts_words_per_second},
            )
        )
        if not isinstance(result, AudioResult):
            raise TypeError("TTS provider synthesize must return AudioResult")
        return result

    @staticmethod
    def _validate_audio_result(
        store: ArtifactStore, result: AudioResult, expected_path: str
    ) -> None:
        if result.status != "completed":
            raise ValueError("TTS result status must be completed")
        if not math.isfinite(result.duration_seconds) or result.duration_seconds <= 0:
            raise ValueError("TTS result duration must be finite and positive")
        if result.output_path != expected_path:
            raise ValueError("TTS result output_path must match the requested project path")
        store.path(result.output_path)

    @staticmethod
    def _validate_scene_ids(scenes: Any) -> list[str]:
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("scenes must be a nonempty list")
        scene_ids: list[str] = []
        for scene in scenes:
            scene_id = scene.get("scene_id") if isinstance(scene, dict) else None
            if not isinstance(scene_id, str) or not scene_id:
                raise ValueError("each scene must have a nonempty scene_id")
            if scene_id in scene_ids:
                raise ValueError(f"duplicate scene_id: {scene_id}")
            scene_ids.append(scene_id)
        return scene_ids

    @staticmethod
    def _validate_payload_inputs(
        store: ArtifactStore,
        scene_ids: list[str],
        timeline: Any,
        images: Any,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        expected = set(scene_ids)
        if not isinstance(timeline, list):
            raise ValueError("timeline must be a list")
        timings: dict[str, dict[str, Any]] = {}
        for timing in timeline:
            timing_id = timing.get("scene_id") if isinstance(timing, dict) else None
            if timing_id in timings:
                raise ValueError(f"duplicate timeline scene_id: {timing_id}")
            if timing_id not in expected:
                raise ValueError(f"unknown timeline scene_id: {timing_id}")
            timings[timing_id] = timing
        missing_timeline = sorted(expected - timings.keys())
        if missing_timeline:
            raise ValueError(f"missing timeline scenes: {', '.join(missing_timeline)}")

        if not isinstance(images, list):
            raise ValueError("generated_images must be a list")
        image_by_scene: dict[str, dict[str, Any]] = {}
        for image in images:
            image_id = image.get("scene_id") if isinstance(image, dict) else None
            if image_id in image_by_scene:
                raise ValueError(f"duplicate generated image scene_id: {image_id}")
            if image_id not in expected:
                raise ValueError(f"unknown generated image scene_id: {image_id}")
            output_path = image.get("output_path")
            if not isinstance(output_path, str) or not output_path:
                raise ValueError(f"generated image for {image_id} has invalid output_path")
            try:
                contained = store.path(output_path)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"generated image for {image_id} has invalid output_path"
                ) from error
            if not contained.is_file():
                raise ValueError(f"generated image for {image_id} output is missing")
            image_by_scene[image_id] = image
        missing_images = sorted(expected - image_by_scene.keys())
        if missing_images:
            raise ValueError(f"missing generated images: {', '.join(missing_images)}")
        return timings, image_by_scene

    @staticmethod
    def _remove_payload(store: ArtifactStore) -> None:
        store.path("render/render_payload.json").unlink(missing_ok=True)

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
