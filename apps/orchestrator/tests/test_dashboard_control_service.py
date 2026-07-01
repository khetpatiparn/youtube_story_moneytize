import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

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
        self._create_project()

        project = self._service().get_project("project_001")

        self.assertEqual(project["projectId"], "project_001")
        self.assertEqual(project["status"], "created")
        self.assertIsNone(project["currentNode"])
        self.assertIsNone(project["waitingFor"])
        self.assertEqual(project["availableActions"], ["run"])

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
        self.assertEqual(projects[0]["status"], "awaiting_script_approval")
        self.assertEqual(projects[0]["currentNode"], "script_approval")
        self.assertEqual(projects[0]["waitingFor"], "script")
        self.assertEqual(projects[0]["availableActions"], ["resume", "approve_script"])

    def test_get_project_returns_explicit_live_summary_shape(self):
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

    def test_rejects_project_ids_outside_projects_directory(self):
        self._create_project()

        with self.assertRaisesRegex(ValueError, "project"):
            self._service().get_project("../outside")

    def test_run_project_uses_runner_factory_and_returns_compact_summary(self):
        from app.services.dashboard_control import DashboardActionAdapter

        self._create_project()
        runner = MagicMock()
        runner.run.return_value = {
            "status": "awaiting_script_approval",
            "current_node": "script_approval",
        }
        runner_factory = MagicMock(return_value=runner)

        result = DashboardActionAdapter(
            self.projects,
            self.checkpoints,
            runner_factory=runner_factory,
        ).run_project("project_001")

        runner_factory.assert_called_once_with("project_001", configure_content=True)
        runner.run.assert_called_once_with("project_001")
        self.assertEqual(
            result,
            {
                "ok": True,
                "projectId": "project_001",
                "action": "run",
                "status": "awaiting_script_approval",
                "currentNode": "script_approval",
                "message": "Project started successfully.",
            },
        )

    def test_resume_project_uses_runner_factory_without_content(self):
        from app.services.dashboard_control import DashboardActionAdapter

        self._create_project()
        runner = MagicMock()
        runner.resume.return_value = {
            "status": "awaiting_final_approval",
            "current_node": "final_approval",
        }
        runner_factory = MagicMock(return_value=runner)

        result = DashboardActionAdapter(
            self.projects,
            self.checkpoints,
            runner_factory=runner_factory,
        ).resume_project("project_001")

        runner_factory.assert_called_once_with("project_001", configure_content=False)
        runner.resume.assert_called_once_with("project_001")
        self.assertEqual(result["action"], "resume")
        self.assertEqual(result["status"], "awaiting_final_approval")
        self.assertEqual(result["currentNode"], "final_approval")

    def test_approve_defaults_reviewer_to_human_and_trims_input(self):
        from app.services.dashboard_control import DashboardActionAdapter

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

        result = DashboardActionAdapter(self.projects, self.checkpoints).approve(
            "script",
            "project_001",
            approved=True,
            reviewer="  ",
        )

        approvals = (
            self.projects.project_dir("project_001") / "reports" / "approvals.json"
        ).read_text(encoding="utf-8")
        self.assertEqual(result["action"], "approve_script")
        self.assertEqual(result["status"], "script_approved")
        self.assertEqual(result["currentNode"], "script_approval")
        self.assertEqual(result["message"], "Script approval recorded.")
        self.assertIn('"reviewer": "human"', approvals)

    def test_approve_rejects_invalid_stage(self):
        from app.services.dashboard_control import DashboardActionAdapter

        self._create_project()

        with self.assertRaisesRegex(ValueError, "stage"):
            DashboardActionAdapter(self.projects, self.checkpoints).approve(
                "draft",
                "project_001",
                approved=True,
                reviewer="human",
            )

    def test_approve_rejects_reviewer_over_64_characters(self):
        from app.services.dashboard_control import DashboardActionAdapter

        self._create_project()

        with self.assertRaisesRegex(ValueError, "reviewer"):
            DashboardActionAdapter(self.projects, self.checkpoints).approve(
                "script",
                "project_001",
                approved=True,
                reviewer="x" * 65,
            )


if __name__ == "__main__":
    unittest.main()
