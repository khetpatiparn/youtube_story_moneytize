import json
import tempfile
import unittest
from pathlib import Path

from app.providers.local import LocalLLMProvider
from app.services.artifacts import ArtifactStore
from app.services.content_pipeline import ContentPipeline


class LocalContentPipelineTests(unittest.TestCase):
    def test_provider_is_deterministic_and_normalizes_topic(self):
        provider = LocalLLMProvider()
        first = provider.generate_story("  The   Moon  ", 42, "en", "calm", 2)
        second = provider.generate_story("The Moon", 42, "en", "calm", 2)

        self.assertEqual(first, second)
        self.assertEqual(first["outline"]["title"], "The Moon")
        self.assertEqual(len(first["scenes"]), 4)
        self.assertEqual(first["script"], "\n\n".join(scene["narration"] for scene in first["scenes"]))

    def test_provider_clamps_scene_count_and_uses_stable_required_fields(self):
        provider = LocalLLMProvider()

        for duration, expected_count in ((1, 3), (999, 8)):
            story = provider.generate_story("Topic", duration, "th", "simple", 1)
            self.assertEqual(len(story["scenes"]), expected_count)
            self.assertEqual(story["outline"].keys(), {"title", "beats"})
            for index, scene in enumerate(story["scenes"], 1):
                self.assertEqual(scene["scene_id"], f"scene_{index:03d}")
                self.assertEqual(
                    set(scene),
                    {"scene_id", "title", "narration", "prompt", "motion", "focal_point"},
                )
                self.assertEqual(scene["motion"], "slow_push")
                self.assertEqual(scene["focal_point"], [0.5, 0.5])

    def test_script_version_changes_deterministic_content(self):
        provider = LocalLLMProvider()
        version_one = provider.generate_story("Topic", 30, "en", "simple", 1)
        version_two = provider.generate_story("Topic", 30, "en", "simple", 2)

        self.assertNotEqual(version_one, version_two)
        self.assertEqual(
            version_two,
            provider.generate_story("Topic", 30, "en", "simple", 2),
        )

    def test_pipeline_writes_artifacts_and_returns_merged_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(Path(temp_dir) / "project_001")
            state = {
                "project_id": "project_001",
                "topic": "  River   Journey ",
                "target_duration_seconds": 55,
                "target_language": "en",
                "channel_style_profile": "simple_story",
                "script_version": 3,
                "created_at": "unchanged",
            }

            result = ContentPipeline(store).generate(state)

            self.assertEqual(result["created_at"], "unchanged")
            self.assertEqual(result["status"], "content_ready")
            self.assertEqual(result["current_node"], "content")
            self.assertEqual(result["script_version"], 3)
            self.assertEqual(result["scene_count"], 6)
            self.assertEqual(result["outline_path"], "content/outline.json")
            self.assertEqual(result["script_path"], "content/script.txt")
            self.assertEqual(result["scenes_path"], "scenes/scenes.json")
            self.assertEqual(store.read_json(result["outline_path"]), result["outline"])
            self.assertEqual(store.read_text(result["script_path"]), result["script"])
            self.assertEqual(store.read_json(result["scenes_path"]), result["scenes"])
            self.assertEqual(
                json.loads((store.root / result["scenes_path"]).read_text(encoding="utf-8")),
                result["scenes"],
            )

    def test_pipeline_output_matches_across_project_roots(self):
        state = {
            "topic": "Same topic",
            "target_duration_seconds": 70,
            "target_language": "en",
            "channel_style_profile": "documentary",
            "script_version": 4,
        }
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_result = ContentPipeline(ArtifactStore(Path(first))).generate(state)
            second_result = ContentPipeline(ArtifactStore(Path(second))).generate(state)

        content_keys = {"outline", "script", "scenes", "scene_count", "script_version"}
        self.assertEqual(
            {key: first_result[key] for key in content_keys},
            {key: second_result[key] for key in content_keys},
        )


if __name__ == "__main__":
    unittest.main()
