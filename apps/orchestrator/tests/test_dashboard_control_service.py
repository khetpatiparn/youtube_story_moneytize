import tempfile
import unittest
from pathlib import Path

from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import CreateProjectRequest


class DashboardControlServiceTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self.projects = ProjectRepository(root / "projects")
        self.checkpoints = CheckpointRepository(root / "checkpoints.sqlite")

    def tearDown(self):
        self._temp_dir.cleanup()

    def _create_project(self, project_id: str = "project_001"):
        return self.projects.create_project(
            CreateProjectRequest(
                topic="A patient river spirit",
                duration=180,
                profile="simple_story_th",
            ),
            project_id=project_id,
        )

    def _service(self):
        from app.services.dashboard_control import DashboardControlService

        return DashboardControlService(self.projects, self.checkpoints)

    def _save_checkpoint(self, project_id: str, **state):
        self.checkpoints.save_checkpoint(
            project_id,
            {
                "project_id": project_id,
                "status": state["status"],
                "current_node": state.get("current_node"),
                "waiting_for": state.get("waiting_for"),
            },
        )

    def test_created_project_without_checkpoint_exposes_run(self):
        self._create_project()

        project = self._service().get_project("project_001")

        self.assertEqual(project["projectId"], "project_001")
        self.assertEqual(project["status"], "created")
        self.assertIsNone(project["currentNode"])
        self.assertIsNone(project["waitingFor"])
        self.assertEqual(project["availableActions"], ["run"])

    def test_missing_checkpoint_keeps_metadata_without_live_node_state(self):
        metadata = self._create_project().with_status("script_changes_requested")
        self.projects.save_project(metadata)

        project = self._service().get_project("project_001")

        self.assertEqual(project["status"], "script_changes_requested")
        self.assertIsNone(project["currentNode"])
        self.assertIsNone(project["waitingFor"])
        self.assertEqual(project["availableActions"], [])

    def test_script_approval_pause_exposes_resume_and_script_approval(self):
        metadata = self._create_project().with_status(
            "awaiting_script_approval",
            current_node="script_approval",
        )
        self.projects.save_project(metadata)
        self._save_checkpoint(
            "project_001",
            status="awaiting_script_approval",
            current_node="script_approval",
            waiting_for="script",
        )

        project = self._service().get_project("project_001")

        self.assertEqual(project["projectId"], "project_001")
        self.assertEqual(project["status"], "awaiting_script_approval")
        self.assertEqual(project["currentNode"], "script_approval")
        self.assertEqual(project["waitingFor"], "script")
        self.assertEqual(project["availableActions"], ["resume", "approve_script"])
        self.assertNotIn("approve_final", project["availableActions"])

    def test_resumable_checkpoint_statuses_expose_resume(self):
        cases = [
            ("script_changes_requested", "script_approval", "script"),
            ("image_generation_failed", "images", None),
            ("awaiting_final_approval", "final_approval", "final"),
            ("quality_validation_failed", "quality", None),
        ]

        for index, (status, current_node, waiting_for) in enumerate(cases, start=1):
            with self.subTest(status=status):
                temp_project = f"project_{index:03d}"
                metadata = self._create_project(temp_project).with_status(
                    status,
                    current_node=current_node,
                )
                self.projects.save_project(metadata)
                self._save_checkpoint(
                    temp_project,
                    status=status,
                    current_node=current_node,
                    waiting_for=waiting_for,
                )

                project = self._service().get_project(temp_project)

                self.assertIn("resume", project["availableActions"])

    def test_final_approval_pause_exposes_resume_and_final_approval(self):
        metadata = self._create_project().with_status(
            "awaiting_final_approval",
            current_node="final_approval",
        )
        self.projects.save_project(metadata)
        self._save_checkpoint(
            "project_001",
            status="awaiting_final_approval",
            current_node="final_approval",
            waiting_for="final",
        )

        project = self._service().get_project("project_001")

        self.assertIn("resume", project["availableActions"])
        self.assertIn("approve_final", project["availableActions"])

    def test_completed_project_exposes_no_actions(self):
        metadata = self._create_project().with_status("completed", current_node="complete")
        self.projects.save_project(metadata)
        self._save_checkpoint(
            "project_001",
            status="completed",
            current_node="complete",
        )

        project = self._service().get_project("project_001")

        self.assertEqual(project["availableActions"], [])

    def test_list_projects_returns_live_summaries(self):
        metadata = self._create_project().with_status(
            "awaiting_script_approval",
            current_node="script_approval",
        )
        self.projects.save_project(metadata)
        self._save_checkpoint(
            "project_001",
            status="awaiting_script_approval",
            current_node="script_approval",
            waiting_for="script",
        )

        projects = self._service().list_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["projectId"], "project_001")
        self.assertEqual(projects[0]["availableActions"], ["resume", "approve_script"])

    def test_rejects_project_ids_outside_projects_directory(self):
        self._create_project()

        with self.assertRaisesRegex(ValueError, "project"):
            self._service().get_project("../outside")


if __name__ == "__main__":
    unittest.main()
