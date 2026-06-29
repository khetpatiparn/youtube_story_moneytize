import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_concurrent_writes_use_isolated_temporary_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(Path(temp_dir) / "project_001")
            contents = {f"writer-{index}" for index in range(8)}
            start_barrier = threading.Barrier(len(contents))
            errors = []

            def write(content):
                try:
                    start_barrier.wait(timeout=2)
                    store.write_text("script/story.md", content)
                except Exception as error:
                    errors.append(error)

            threads = [
                threading.Thread(target=write, args=(content,))
                for content in contents
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            self.assertIn(store.read_text("script/story.md"), contents)

    def test_removes_temporary_file_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(Path(temp_dir) / "project_001")

            with patch("app.services.artifacts.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    store.write_text("script/story.md", "content")

            script_dir = store.root / "script"
            self.assertEqual(list(script_dir.glob("*tmp*")), [])


if __name__ == "__main__":
    unittest.main()
