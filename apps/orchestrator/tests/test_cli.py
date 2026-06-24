import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_create_and_status_commands_use_project_directory(self):
        source_dir = Path(__file__).resolve().parents[1] / "src"

        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(source_dir)
            checkpoint_db = str(Path(temp_dir) / "checkpoints.sqlite")

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
            self.assertEqual(run_payload["status"], "initialized")
            self.assertEqual(run_payload["current_node"], "initialize_project")
            self.assertTrue(Path(checkpoint_db).is_file())

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
            self.assertEqual(resume_payload["status"], "initialized")
            self.assertEqual(resume_payload["current_node"], "initialize_project")

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


if __name__ == "__main__":
    unittest.main()
