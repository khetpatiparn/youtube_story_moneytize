from __future__ import annotations

import json
from typing import Any

from app.providers.base import RetryableProviderError
from app.services.artifacts import ArtifactStore


class ImageGenerationExhausted(RuntimeError):
    def __init__(self, failed_scene_ids: list[str], result: dict[str, Any] | None = None) -> None:
        self.failed_scene_ids = failed_scene_ids
        self.result = result or {}
        super().__init__(f"Image generation exhausted for: {', '.join(failed_scene_ids)}")


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
        prior = {job["scene_id"]: dict(job) for job in existing_jobs or []}
        jobs: list[dict[str, Any]] = []
        scene_by_id = {scene["scene_id"]: dict(scene) for scene in scenes}
        for scene in scenes:
            scene_id = scene["scene_id"]
            job = prior.get(scene_id)
            if job is None:
                job = {
                    "scene_id": scene_id,
                    "status": "pending",
                    "attempts": 0,
                    "retry_count": 0,
                    "error": None,
                }
            jobs.append(job)
            if job.get("status") == "completed" and job.get("output_path"):
                scene_by_id[scene_id]["image_path"] = job["output_path"]

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
                    job["retry_count"] = max(job["attempts"] - 1, 0)
                    job["error"] = str(error)
                    if job["attempts"] < self.max_attempts:
                        job["status"] = "retrying"
                        retry_pending.append(job)
                    else:
                        job["status"] = "failed"
                    continue
                job.update(image)
                job["status"] = "completed"
                job["error"] = None
                job["retry_count"] = max(job["attempts"] - 1, 0)
                scene["image_path"] = image["output_path"]
            pending = retry_pending

        published_scenes = [scene_by_id[scene["scene_id"]] for scene in scenes]
        self.store.publish_bytes_set(
            {
                "images/jobs.json": self._json_bytes(jobs),
                "scenes/scenes.json": self._json_bytes(published_scenes),
            }
        )
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
        result = {
            "scenes": published_scenes,
            "image_jobs": jobs,
            "generated_images": generated,
            "failed_scene_ids": failed,
            "retry_counts": {job["scene_id"]: job["retry_count"] for job in jobs},
        }
        if failed:
            raise ImageGenerationExhausted(failed, result)
        return result

    @staticmethod
    def _json_bytes(content: Any) -> bytes:
        return (json.dumps(content, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
