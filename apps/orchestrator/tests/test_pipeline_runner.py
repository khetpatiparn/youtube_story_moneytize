import json
import tempfile
import unittest
from pathlib import Path


class PipelineRunnerTests(unittest.TestCase):
    def _setup(self, temp_dir: str):
        from app.repositories.checkpoint_repository import CheckpointRepository
        from app.repositories.project_repository import ProjectRepository
        from app.schemas.project import CreateProjectRequest

        projects = ProjectRepository(Path(temp_dir) / "projects")
        projects.create_project(
            CreateProjectRequest(topic="A patient river spirit", duration=180, profile="simple_story_th"),
            project_id="project_001",
        )
        return projects, CheckpointRepository(Path(temp_dir) / "checkpoints.sqlite")

    def test_first_run_persists_script_approval_pause(self):
        from app.services.pipeline_runner import PipelineRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            projects, checkpoints = self._setup(temp_dir)
            state = PipelineRunner(projects, checkpoints).run("project_001")

            self.assertEqual(state["status"], "awaiting_script_approval")
            self.assertEqual(state["current_node"], "script_approval")
            self.assertEqual(state["waiting_for"], "script")
            self.assertEqual(checkpoints.load_latest("project_001").state, state)
            metadata = projects.load_project("project_001")
            self.assertEqual(metadata.status, state["status"])
            self.assertEqual(metadata.current_node, state["current_node"])

    def test_resume_without_approval_returns_checkpoint_without_modifying_artifacts(self):
        from app.services.pipeline_runner import PipelineRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            projects, checkpoints = self._setup(temp_dir)
            state = PipelineRunner(projects, checkpoints).run("project_001")
            project_dir = projects.project_dir("project_001")
            before = {p.relative_to(project_dir).as_posix(): p.read_bytes() for p in project_dir.rglob("*") if p.is_file()}

            resumed = PipelineRunner(projects, checkpoints).resume("project_001")
            after = {p.relative_to(project_dir).as_posix(): p.read_bytes() for p in project_dir.rglob("*") if p.is_file()}

            self.assertEqual(resumed, state)
            self.assertEqual(after, before)

    def test_repeated_run_is_idempotent(self):
        from app.services.pipeline_runner import PipelineRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            projects, checkpoints = self._setup(temp_dir)
            runner = PipelineRunner(projects, checkpoints)
            first = runner.run("project_001")
            project_dir = projects.project_dir("project_001")
            before = (project_dir / "content" / "script.txt").read_bytes()
            second = runner.run("project_001")
            self.assertEqual(second, first)
            self.assertEqual((project_dir / "content" / "script.txt").read_bytes(), before)

    def test_resume_requires_checkpoint(self):
        from app.services.pipeline_runner import PipelineRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            projects, checkpoints = self._setup(temp_dir)
            with self.assertRaisesRegex(ValueError, "No checkpoint found"):
                PipelineRunner(projects, checkpoints).resume("project_001")

    def test_script_approval_updates_checkpoint_for_new_service_instance(self):
        from app.services.approval_reporting import ApprovalReportingService, ApprovalRequest
        from app.services.pipeline_runner import PipelineRunner

        with tempfile.TemporaryDirectory() as temp_dir:
            projects, checkpoints = self._setup(temp_dir)
            PipelineRunner(projects, checkpoints).run("project_001")
            ApprovalReportingService(projects, checkpoints).record_script_approval(
                ApprovalRequest("project_001", True, "human")
            )

            state = PipelineRunner(projects, checkpoints).resume("project_001")
            self.assertTrue(state["script_approved"])
            self.assertEqual(state["status"], "script_approved")
            self.assertEqual(state["current_node"], "script_approval")
            self.assertNotIn("waiting_for", state)


if __name__ == "__main__":
    unittest.main()
