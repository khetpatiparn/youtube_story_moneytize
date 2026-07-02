import json
import tempfile
import unittest
from pathlib import Path

from app.repositories.project_repository import ProjectRepository
from app.schemas.project import CreateProjectRequest
from app.services.artifacts import ArtifactStore


class ScriptEditorTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self.projects = ProjectRepository(root / "projects")
        self.metadata = self.projects.create_project(
            CreateProjectRequest(
                topic="A patient river spirit",
                duration=180,
                profile="simple_story_th",
            ),
            project_id="project_001",
        )
        self.project_dir = self.projects.project_dir("project_001")
        self.store = ArtifactStore(self.project_dir)
        self.original_scenes = [
            {
                "scene_id": "scene_001",
                "title": "Opening",
                "narration": "First narration",
                "prompt": "First prompt",
                "motion": "slow_push",
                "focal_point": [0.5, 0.5],
            },
            {
                "scene_id": "scene_002",
                "title": "Middle",
                "narration": "Second narration",
                "prompt": "Second prompt",
                "motion": "slow_push",
                "focal_point": [0.5, 0.5],
            },
        ]
        self.store.publish_bytes_set(
            {
                "content/script.txt": "First narration\n\nSecond narration".encode("utf-8"),
                "scenes/scenes.json": (json.dumps(self.original_scenes, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            }
        )

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_read_returns_revision_and_normalized_scenes(self):
        from app.services.script_editor import ScriptEditor

        editor = ScriptEditor(self.projects)
        current = editor.read("project_001")

        self.assertIsInstance(current["revision"], str)
        self.assertEqual(len(current["scenes"]), 2)
        self.assertEqual(current["scenes"][0]["sceneId"], "scene_001")
        self.assertEqual(current["scenes"][0]["narration"], "First narration")
        self.assertEqual(current["scenes"][0]["prompt"], "First prompt")

    def test_update_rejects_stale_revision(self):
        from app.services.script_editor import ScriptEditor

        editor = ScriptEditor(self.projects)
        current = editor.read("project_001")
        editor.update(
            "project_001",
            current["revision"],
            [{"sceneId": "scene_001", "narration": "new", "prompt": "p"}],
        )

        with self.assertRaisesRegex(ValueError, "revision"):
            editor.update("project_001", current["revision"], [])

    def test_update_replaces_scene_and_script_atomically(self):
        from app.services.script_editor import ScriptEditor

        editor = ScriptEditor(self.projects)
        current = editor.read("project_001")

        updated = editor.update(
            "project_001",
            current["revision"],
            [
                {"sceneId": "scene_001", "narration": "Updated first", "prompt": "Updated prompt"},
                {"sceneId": "scene_002", "narration": "Updated second", "prompt": "Updated prompt 2"},
            ],
        )

        scenes = json.loads((self.project_dir / "scenes" / "scenes.json").read_text(encoding="utf-8"))
        script_text = (self.project_dir / "content" / "script.txt").read_text(encoding="utf-8")
        self.assertEqual(updated["scenes"][0]["narration"], "Updated first")
        self.assertEqual(scenes[0]["narration"], "Updated first")
        self.assertEqual(script_text, "Updated first\n\nUpdated second")


if __name__ == "__main__":
    unittest.main()
