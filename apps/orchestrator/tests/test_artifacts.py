import tempfile
import unittest
from pathlib import Path

from app.services.artifacts import ArtifactStore


class ArtifactStoreTests(unittest.TestCase):
    def test_text_and_json_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project_001"
            store = ArtifactStore(project_root)

            text_path = store.write_text("script/story.md", "สวัสดี\n")
            json_path = store.write_json(
                "scenes/scenes.json",
                {"title": "นิทาน", "scenes": [1, 2]},
            )

            self.assertEqual(store.root, project_root.resolve())
            self.assertEqual(text_path, "script/story.md")
            self.assertEqual(json_path, "scenes/scenes.json")
            self.assertEqual(store.read_text(text_path), "สวัสดี\n")
            self.assertEqual(
                store.read_json(json_path),
                {"title": "นิทาน", "scenes": [1, 2]},
            )
            self.assertEqual(
                (project_root / "scenes" / "scenes.json").read_text(encoding="utf-8"),
                '{\n  "title": "นิทาน",\n  "scenes": [\n    1,\n    2\n  ]\n}\n',
            )
            self.assertFalse((project_root / "script" / "story.md.tmp").exists())

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(Path(temp_dir) / "project_001")

            with self.assertRaises(ValueError):
                store.path("../outside.txt")

    def test_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(Path(temp_dir) / "project_001")

            with self.assertRaises(ValueError):
                store.path((Path(temp_dir) / "outside.txt").resolve())


if __name__ == "__main__":
    unittest.main()
