from __future__ import annotations

from app.providers.local import LocalLLMProvider
from app.schemas.state import VideoProjectState
from app.services.artifacts import ArtifactStore


class ContentPipeline:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        provider: LocalLLMProvider | None = None,
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

        outline_path = self.artifact_store.write_json("content/outline.json", content["outline"])
        script_path = self.artifact_store.write_text("content/script.txt", content["script"])
        scenes_path = self.artifact_store.write_json("scenes/scenes.json", content["scenes"])

        return {
            **state,
            **content,
            "scene_count": len(content["scenes"]),
            "script_version": script_version,
            "status": "content_ready",
            "current_node": "content",
            "outline_path": outline_path,
            "script_path": script_path,
            "scenes_path": scenes_path,
        }
