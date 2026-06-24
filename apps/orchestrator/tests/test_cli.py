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


if __name__ == "__main__":
    unittest.main()
