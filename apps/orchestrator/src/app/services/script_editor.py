from __future__ import annotations

import hashlib
import json
from typing import Any

from app.repositories.project_repository import ProjectRepository
from app.services.artifacts import ArtifactStore


class ScriptEditor:
    def __init__(self, projects: ProjectRepository) -> None:
        self.projects = projects

    def read(self, project_id: str) -> dict[str, object]:
        store = ArtifactStore(self.projects.project_dir(project_id))
        scenes = store.read_json("scenes/scenes.json")
        if not isinstance(scenes, list):
            raise ValueError("scenes/scenes.json must contain a list")
        normalized = [self._normalize_scene(scene) for scene in scenes]
        return {"revision": self._revision_for(normalized), "scenes": normalized}

    def update(self, project_id: str, revision: str, scenes: list[dict[str, object]]) -> dict[str, object]:
        current = self.read(project_id)
        if revision != current["revision"]:
            raise ValueError("revision does not match current script")

        normalized = [self._validate_update_scene(scene) for scene in scenes]
        project_dir = self.projects.project_dir(project_id)
        store = ArtifactStore(project_dir)
        script_text = "\n\n".join(scene["narration"] for scene in normalized)
        published = [
            {
                "scene_id": scene["sceneId"],
                "title": self._title_for_scene_id(scene["sceneId"]),
                "narration": scene["narration"],
                "prompt": scene["prompt"],
                "motion": "slow_push",
                "focal_point": [0.5, 0.5],
            }
            for scene in normalized
        ]
        store.publish_bytes_set(
            {
                "content/script.txt": script_text.encode("utf-8"),
                "scenes/scenes.json": (json.dumps(published, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            }
        )
        return self.read(project_id)

    def _normalize_scene(self, scene: Any) -> dict[str, str]:
        if not isinstance(scene, dict):
            raise ValueError("scene must be an object")
        return {
            "sceneId": str(scene.get("sceneId") or scene.get("scene_id") or ""),
            "narration": str(scene.get("narration") or ""),
            "prompt": str(scene.get("prompt") or ""),
        }

    def _validate_update_scene(self, scene: Any) -> dict[str, str]:
        normalized = self._normalize_scene(scene)
        if not normalized["sceneId"]:
            raise ValueError("sceneId is required")
        if not normalized["narration"]:
            raise ValueError("narration is required")
        if not normalized["prompt"]:
            raise ValueError("prompt is required")
        return normalized

    def _revision_for(self, scenes: list[dict[str, str]]) -> str:
        canonical = json.dumps(scenes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _title_for_scene_id(self, scene_id: str) -> str:
        return scene_id.replace("_", " ").title()
