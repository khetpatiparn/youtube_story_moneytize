from __future__ import annotations

import json
from typing import Any
from xml.etree import ElementTree

from app.providers.base import PermanentProviderError, RetryableProviderError
from app.services.artifacts import ArtifactStore


class ImageGenerationExhausted(RuntimeError):
    def __init__(self, failed_scene_ids: list[str], result: dict[str, Any] | None = None) -> None:
        self.failed_scene_ids = failed_scene_ids
        self.result = result or {}
        super().__init__(f"Image generation exhausted for: {', '.join(failed_scene_ids)}")


class PersistedImageJobError(PermanentProviderError):
    """A durable completed job is unsafe or corrupt and cannot be reused."""


class ImagePipeline:
    def __init__(self, store: ArtifactStore, provider: Any, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.store = store
        self.provider = provider
        self.max_attempts = max_attempts

    def generate(
        self,
        scenes: list[dict[str, Any]],
        existing_jobs: list[dict[str, Any]] | None = None,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if existing_jobs is None and state is not None:
            existing_jobs = state.get("image_jobs")
        if existing_jobs is None and self.store.path("images/jobs.json").is_file():
            loaded = self.store.read_json("images/jobs.json")
            if not isinstance(loaded, list):
                raise PersistedImageJobError("images/jobs.json must contain a list")
            existing_jobs = loaded

        scene_by_id = {scene["scene_id"]: dict(scene) for scene in scenes}
        known_scene_ids = set(scene_by_id)
        prior: dict[str, dict[str, Any]] = {}
        for candidate in existing_jobs or []:
            if not isinstance(candidate, dict):
                raise PersistedImageJobError("persisted image job must be an object")
            candidate_scene_id = candidate.get("scene_id")
            if candidate_scene_id not in known_scene_ids:
                raise PersistedImageJobError(
                    f"persisted image job {candidate_scene_id!r} has no corresponding scene"
                )
            prior[candidate_scene_id] = dict(candidate)

        jobs: list[dict[str, Any]] = []
        terminal_error: PermanentProviderError | None = None
        for scene in scenes:
            scene_id = scene["scene_id"]
            job = prior.get(scene_id) or self._new_job(scene_id)
            jobs.append(job)
            if job.get("status") == "permanent_failed":
                terminal_error = PermanentProviderError(str(job.get("error") or "permanent image failure"))
                continue
            if job.get("status") == "unexpected_failed":
                terminal_error = PersistedImageJobError(
                    f"persisted unexpected image failure for {scene_id}: {job.get('error', '')}"
                )
                continue
            if job.get("status") == "completed":
                corruption = self._completed_job_corruption(job, scene_id)
                if corruption is None:
                    scene_by_id[scene_id]["image_path"] = job["output_path"]
                elif int(job.get("attempts", 0)) < self.max_attempts:
                    job.update(status="pending", error=corruption)
                    for key in ("output_path", "mime_type", "provider", "model", "prompt_hash"):
                        job.pop(key, None)
                else:
                    message = f"corrupt completed image job for {scene_id}: {corruption}"
                    job.update(status="permanent_failed", error=message)
                    terminal_error = PersistedImageJobError(message)

        if terminal_error is not None:
            self._publish(jobs, scene_by_id, scenes)
            raise terminal_error

        pending = [
            job
            for job in jobs
            if job.get("status") != "completed" and int(job.get("attempts", 0)) < self.max_attempts
        ]
        for job in jobs:
            if job.get("status") != "completed" and int(job.get("attempts", 0)) >= self.max_attempts:
                job["status"] = "failed"

        while pending:
            retry_pending: list[dict[str, Any]] = []
            for job in pending:
                scene_id = job["scene_id"]
                scene = scene_by_id[scene_id]
                job["attempts"] = int(job.get("attempts", 0)) + 1
                try:
                    image = self.provider.generate(scene, f"images/{scene_id}.svg")
                except RetryableProviderError as error:
                    job.update(
                        retry_count=max(job["attempts"] - 1, 0),
                        error=str(error),
                        status="retrying" if job["attempts"] < self.max_attempts else "failed",
                    )
                    self._publish(jobs, scene_by_id, scenes)
                    if job["status"] == "retrying":
                        retry_pending.append(job)
                    continue
                except PermanentProviderError as error:
                    job.update(
                        status="permanent_failed",
                        retry_count=max(job["attempts"] - 1, 0),
                        error=str(error),
                        error_type=type(error).__name__,
                    )
                    self._publish(jobs, scene_by_id, scenes)
                    raise
                except Exception as error:
                    job.update(
                        status="unexpected_failed",
                        retry_count=max(job["attempts"] - 1, 0),
                        error=str(error),
                        error_type=type(error).__name__,
                    )
                    self._publish(jobs, scene_by_id, scenes)
                    raise
                job.update(image)
                job.update(
                    status="completed",
                    error=None,
                    retry_count=max(job["attempts"] - 1, 0),
                )
                job.pop("error_type", None)
                validation_error = self._completed_job_corruption(job, scene_id)
                if validation_error is not None:
                    job.update(
                        status="retrying" if job["attempts"] < self.max_attempts else "failed",
                        error=validation_error,
                    )
                    self._publish(jobs, scene_by_id, scenes)
                    if job["status"] == "retrying":
                        retry_pending.append(job)
                    continue
                scene["image_path"] = image["output_path"]
                self._publish(jobs, scene_by_id, scenes)
            pending = retry_pending

        result = self._result(jobs, scene_by_id, scenes)
        self._publish(jobs, scene_by_id, scenes)
        if result["failed_scene_ids"]:
            raise ImageGenerationExhausted(result["failed_scene_ids"], result)
        return result

    @staticmethod
    def _new_job(scene_id: str) -> dict[str, Any]:
        return {
            "scene_id": scene_id,
            "status": "pending",
            "attempts": 0,
            "retry_count": 0,
            "error": None,
        }

    def _completed_job_corruption(self, job: dict[str, Any], scene_id: str) -> str | None:
        required = {"scene_id", "status", "attempts", "output_path", "mime_type"}
        missing = sorted(required - job.keys())
        if missing:
            return f"missing required fields: {', '.join(missing)}"
        if job["scene_id"] != scene_id:
            return "scene_id does not match scene"
        if not isinstance(job["attempts"], int) or job["attempts"] < 1:
            return "attempts must be a positive integer"
        if job["mime_type"] != "image/svg+xml":
            return "mime_type must be image/svg+xml"
        try:
            path = self.store.path(job["output_path"])
        except (TypeError, ValueError):
            return "output_path is not a contained project-relative path"
        if not path.is_file() or path.stat().st_size == 0:
            return "output file is missing or empty"
        try:
            root = ElementTree.fromstring(path.read_bytes())
        except (ElementTree.ParseError, OSError):
            return "output SVG is not parseable"
        if root.tag != "{http://www.w3.org/2000/svg}svg":
            return "output XML root must be the SVG namespace element"
        expected_canvas = {
            "width": "1280",
            "height": "720",
            "viewBox": "0 0 1280 720",
        }
        for attribute, expected in expected_canvas.items():
            if root.get(attribute) != expected:
                return f"output SVG {attribute} must be {expected!r}"
        return None

    def _publish(
        self,
        jobs: list[dict[str, Any]],
        scene_by_id: dict[str, dict[str, Any]],
        source_scenes: list[dict[str, Any]],
    ) -> None:
        published_scenes = [scene_by_id[scene["scene_id"]] for scene in source_scenes]
        self.store.publish_bytes_set(
            {
                "images/jobs.json": self._json_bytes(jobs),
                "scenes/scenes.json": self._json_bytes(published_scenes),
            }
        )

    def _result(
        self,
        jobs: list[dict[str, Any]],
        scene_by_id: dict[str, dict[str, Any]],
        source_scenes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        generated = [
            {
                "scene_id": job["scene_id"],
                "output_path": job["output_path"],
                "mime_type": job["mime_type"],
            }
            for job in jobs
            if job["status"] == "completed"
        ]
        failed = [job["scene_id"] for job in jobs if job["status"] == "failed"]
        return {
            "scenes": [scene_by_id[scene["scene_id"]] for scene in source_scenes],
            "image_jobs": jobs,
            "generated_images": generated,
            "failed_scene_ids": failed,
            "retry_counts": {job["scene_id"]: int(job.get("retry_count", 0)) for job in jobs},
        }

    @staticmethod
    def _json_bytes(content: Any) -> bytes:
        return (json.dumps(content, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
