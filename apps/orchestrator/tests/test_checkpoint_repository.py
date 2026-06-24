import tempfile
import unittest
from pathlib import Path


class CheckpointRepositoryTests(unittest.TestCase):
    def test_save_and_load_latest_checkpoint_by_project_id_thread(self):
        from app.repositories.checkpoint_repository import CheckpointRepository

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = CheckpointRepository(Path(temp_dir) / "checkpoints.sqlite")
            state = {
                "project_id": "project_001",
                "status": "initialized",
                "current_node": "initialize_project",
                "topic": "A small kindness becomes a legend",
            }

            record = repository.save_checkpoint("project_001", state)
            loaded = repository.load_latest("project_001")

            self.assertEqual(record.thread_id, "project_001")
            self.assertEqual(loaded.thread_id, "project_001")
            self.assertEqual(loaded.state["project_id"], "project_001")
            self.assertEqual(loaded.state["status"], "initialized")
            self.assertEqual(loaded.state["current_node"], "initialize_project")
            self.assertTrue(repository.db_path.is_file())

    def test_missing_checkpoint_returns_none(self):
        from app.repositories.checkpoint_repository import CheckpointRepository

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = CheckpointRepository(Path(temp_dir) / "checkpoints.sqlite")

            self.assertIsNone(repository.load_latest("missing_project"))


if __name__ == "__main__":
    unittest.main()
