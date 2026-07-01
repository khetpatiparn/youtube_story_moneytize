import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class CliTests(unittest.TestCase):
    def test_pipeline_runner_injects_story_provider_only_for_fresh_run(self):
        from app.cli.main import _build_pipeline_runner

        repository = MagicMock()
        repository.project_dir.return_value = Path("project-root")
        checkpoints = MagicMock()
        checkpoints.load_latest.return_value = None
        runner = object()
        story_provider = object()
        args = SimpleNamespace(
            projects_dir="projects",
            checkpoint_db="checkpoints.sqlite",
            project_id="project_001",
            max_image_attempts=3,
            tts_words_per_second=2.5,
        )

        with (
            patch("app.cli.main.ProjectRepository", return_value=repository),
            patch("app.cli.main.CheckpointRepository", return_value=checkpoints),
            patch("app.cli.main.RemotionRenderer"),
            patch("app.cli.main.build_story_provider", return_value=story_provider) as build_story,
            patch("app.cli.main.build_image_provider") as build_image,
            patch("app.cli.main.build_tts_provider") as build_tts,
            patch("app.cli.main.PipelineRunner", return_value=runner) as runner_type,
        ):
            result = _build_pipeline_runner(args, configure_content=True)

        self.assertIs(result, runner)
        build_story.assert_called_once()
        build_image.assert_not_called()
        build_tts.assert_not_called()
        self.assertIs(runner_type.call_args.kwargs["content_provider"], story_provider)

    def test_non_run_commands_do_not_construct_story_provider(self):
        from app.cli.main import _build_pipeline_runner

        repository = MagicMock()
        repository.project_dir.return_value = Path("project-root")
        checkpoints = MagicMock()
        checkpoints.load_latest.return_value = None
        args = SimpleNamespace(
            projects_dir="projects",
            checkpoint_db="checkpoints.sqlite",
            project_id="project_001",
            max_image_attempts=3,
            tts_words_per_second=2.5,
        )

        with (
            patch("app.cli.main.ProjectRepository", return_value=repository),
            patch("app.cli.main.CheckpointRepository", return_value=checkpoints),
            patch("app.cli.main.RemotionRenderer"),
            patch("app.cli.main.build_story_provider") as build_story,
            patch("app.cli.main.PipelineRunner"),
        ):
            _build_pipeline_runner(args, configure_content=False)
        build_story.assert_not_called()

    def test_pipeline_runner_injects_selected_media_providers_after_script_approval(self):
        from app.cli.main import _build_pipeline_runner

        repository = MagicMock()
        repository.project_dir.return_value = Path("project-root")
        checkpoints = MagicMock()
        checkpoints.load_latest.return_value = SimpleNamespace(
            state={"script_approved": True}
        )
        image_provider = object()
        tts_provider = object()
        runner = object()
        args = SimpleNamespace(
            projects_dir="projects",
            checkpoint_db="checkpoints.sqlite",
            project_id="project_001",
            max_image_attempts=3,
            tts_words_per_second=2.5,
        )

        with (
            patch("app.cli.main.ProjectRepository", return_value=repository),
            patch("app.cli.main.CheckpointRepository", return_value=checkpoints),
            patch("app.cli.main.RemotionRenderer"),
            patch("app.cli.main.build_story_provider") as build_story,
            patch("app.cli.main.build_image_provider", return_value=image_provider) as build_image,
            patch("app.cli.main.build_tts_provider", return_value=tts_provider) as build_tts,
            patch("app.cli.main.PipelineRunner", return_value=runner) as runner_type,
        ):
            result = _build_pipeline_runner(args, configure_content=False)

        self.assertIs(result, runner)
        build_story.assert_not_called()
        build_image.assert_called_once()
        build_tts.assert_called_once()
        self.assertIs(runner_type.call_args.kwargs["image_provider"], image_provider)
        self.assertIs(runner_type.call_args.kwargs["tts_provider"], tts_provider)

    def test_create_and_status_commands_use_project_directory(self):
        source_dir = Path(__file__).resolve().parents[1] / "src"

        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(source_dir)
            checkpoint_db = str(Path(temp_dir) / "checkpoints.sqlite")
            env["CHECKPOINT_DB"] = checkpoint_db
            env["TTS_PROVIDER"] = "local"
            env["IMAGE_PROVIDER"] = "local"
            env["LLM_PROVIDER"] = "local"

            create_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "create",
                    "--topic",
                    "A river spirit teaches patience",
                    "--duration",
                    "180",
                    "--profile",
                    "simple_story_th",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(create_result.returncode, 0, create_result.stderr)
            create_payload = json.loads(create_result.stdout)
            self.assertEqual(create_payload["project_id"], "project_001")

            status_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "status",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(status_result.returncode, 0, status_result.stderr)
            status_payload = json.loads(status_result.stdout)
            self.assertEqual(status_payload["project_id"], "project_001")
            self.assertEqual(status_payload["status"], "created")

            run_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "run",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                    "--checkpoint-db",
                    checkpoint_db,
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(run_result.returncode, 0, run_result.stderr)
            run_payload = json.loads(run_result.stdout)
            self.assertEqual(run_payload["project_id"], "project_001")
            self.assertEqual(run_payload["status"], "awaiting_script_approval")
            self.assertEqual(run_payload["current_node"], "script_approval")
            self.assertEqual(run_payload["waiting_for"], "script")
            self.assertTrue(Path(checkpoint_db).is_file())

            env["TTS_PROVIDER"] = "unknown-but-unused-before-approval"
            env["IMAGE_PROVIDER"] = "unknown-but-unused-before-approval"
            env["LLM_PROVIDER"] = "unknown-but-unused-before-approval"
            resume_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "resume",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                    "--checkpoint-db",
                    checkpoint_db,
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(resume_result.returncode, 0, resume_result.stderr)
            resume_payload = json.loads(resume_result.stdout)
            self.assertEqual(resume_payload["project_id"], "project_001")
            self.assertEqual(resume_payload["status"], "awaiting_script_approval")
            self.assertEqual(resume_payload["current_node"], "script_approval")
            env["LLM_PROVIDER"] = "local"
            env["TTS_PROVIDER"] = "local"
            env["IMAGE_PROVIDER"] = "local"

            script_approval_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "approve-script",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                    "--approved",
                    "--reviewer",
                    "human",
                    "--notes",
                    "Script ready.",
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(script_approval_result.returncode, 0, script_approval_result.stderr)
            script_approval_payload = json.loads(script_approval_result.stdout)
            self.assertEqual(script_approval_payload["stage"], "script")
            self.assertTrue(script_approval_payload["approved"])
            from app.repositories.checkpoint_repository import CheckpointRepository

            saved = CheckpointRepository(Path(checkpoint_db)).load_latest("project_001")
            self.assertTrue(saved.state["script_approved"])
            CheckpointRepository(Path(checkpoint_db)).save_checkpoint(
                "project_001",
                {
                    **saved.state,
                    "status": "awaiting_final_approval",
                    "current_node": "final_approval",
                    "waiting_for": "final",
                },
            )

            final_approval_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "approve-final",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                    "--changes-requested",
                    "--reviewer",
                    "human",
                    "--notes",
                    "Audio needs balancing.",
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(final_approval_result.returncode, 0, final_approval_result.stderr)
            final_approval_payload = json.loads(final_approval_result.stdout)
            self.assertEqual(final_approval_payload["stage"], "final")
            self.assertFalse(final_approval_payload["approved"])

            report_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "report",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                    "--video-path",
                    "render/story.mp4",
                    "--quality-score",
                    "0.91",
                    "--issue",
                    "No final approval yet",
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertEqual(report_result.returncode, 0, report_result.stderr)
            report_payload = json.loads(report_result.stdout)
            self.assertEqual(report_payload["quality_report_path"], "reports/quality_report.json")
            self.assertEqual(report_payload["contact_sheet_path"], "reports/contact_sheet.md")
            self.assertEqual(report_payload["project_report_path"], "reports/project_report.md")

    def test_run_with_invalid_story_provider_fails_before_writing_checkpoint(self):
        source_dir = Path(__file__).resolve().parents[1] / "src"

        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(source_dir)
            checkpoint_db = str(Path(temp_dir) / "checkpoints.sqlite")
            env["CHECKPOINT_DB"] = checkpoint_db
            env["LLM_PROVIDER"] = "local"
            env["TTS_PROVIDER"] = "local"
            env["IMAGE_PROVIDER"] = "local"

            create_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "create",
                    "--topic",
                    "A river spirit teaches patience",
                    "--duration",
                    "180",
                    "--profile",
                    "simple_story_th",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )
            self.assertEqual(create_result.returncode, 0, create_result.stderr)

            env["LLM_PROVIDER"] = "unknown"
            run_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app",
                    "run",
                    "--project-id",
                    "project_001",
                    "--projects-dir",
                    temp_dir,
                    "--checkpoint-db",
                    checkpoint_db,
                ],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

            self.assertNotEqual(run_result.returncode, 0)
            self.assertIn("LLM_PROVIDER", run_result.stderr)
            from app.repositories.checkpoint_repository import CheckpointRepository

            self.assertIsNone(
                CheckpointRepository(Path(checkpoint_db)).load_latest("project_001")
            )
            self.assertFalse((Path(temp_dir) / "project_001" / "content").exists())


if __name__ == "__main__":
    unittest.main()
