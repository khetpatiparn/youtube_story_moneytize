from __future__ import annotations

import json
from typing import Any, Protocol

from app.providers.local import LocalLLMProvider
from app.schemas.state import VideoProjectState
from app.services.artifacts import ArtifactStore


class StoryProvider(Protocol):
    def generate_story(
        self,
        topic: str,
        duration_seconds: int,
        language: str,
        profile: str,
        script_version: int,
    ) -> dict[str, Any]: ...


class ContentPipeline:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        provider: StoryProvider | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.provider = provider or LocalLLMProvider()

    def generate(self, state: VideoProjectState) -> VideoProjectState:
        script_version = state.get("script_version", 1)
        content = self.provider.generate_story(
            state["topic"],
            state["target_duration_seconds"],
            state["target_language"],
            state["channel_style_profile"],
            script_version,
        )
        validate_story_content(content)

        serialized = {
            "content/outline.json": self._json_bytes(content["outline"]),
            "content/script.txt": content["script"].encode("utf-8"),
            "scenes/scenes.json": self._json_bytes(content["scenes"]),
        }
        paths = self.artifact_store.publish_bytes_set(serialized)

        return {
            **state,
            **content,
            "scene_count": len(content["scenes"]),
            "script_version": script_version,
            "content_provider": getattr(self.provider, "provider", "unknown"),
            "content_model": getattr(self.provider, "model", "unknown"),
            "status": "content_ready",
            "current_node": "content",
            "outline_path": paths["content/outline.json"],
            "script_path": paths["content/script.txt"],
            "scenes_path": paths["scenes/scenes.json"],
        }

    @staticmethod
    def _json_bytes(content: Any) -> bytes:
        return (json.dumps(content, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def validate_story_content(content: Any) -> None:
    if not isinstance(content, dict) or set(content) != {"outline", "script", "scenes"}:
        raise ValueError("Invalid provider output: expected outline, script, and scenes")
    outline = content["outline"]
    scenes = content["scenes"]
    if (
        not isinstance(outline, dict)
        or set(outline) != {"title", "beats"}
        or not isinstance(outline["title"], str)
        or not isinstance(outline["beats"], list)
        or not isinstance(content["script"], str)
        or not isinstance(scenes, list)
        or not scenes
    ):
        raise ValueError("Invalid provider output shape")
    required_scene_keys = {"scene_id", "title", "narration", "prompt", "motion", "focal_point"}
    for index, scene in enumerate(scenes, 1):
        if (
            not isinstance(scene, dict)
            or set(scene) != required_scene_keys
            or scene["scene_id"] != f"scene_{index:03d}"
            or scene["motion"] != "slow_push"
            or scene["focal_point"] != [0.5, 0.5]
            or any(not isinstance(scene[key], str) for key in ("title", "narration", "prompt"))
        ):
            raise ValueError("Invalid provider output scene")
    if outline["beats"] != [scene["title"] for scene in scenes]:
        raise ValueError("Invalid provider output beats")
    if content["script"] != "\n\n".join(scene["narration"] for scene in scenes):
        raise ValueError("Invalid provider output script")
