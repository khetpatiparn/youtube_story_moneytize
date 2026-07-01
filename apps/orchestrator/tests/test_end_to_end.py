import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class EndToEndLocalPipelineTests(unittest.TestCase):
    def test_cli_processes_create_render_review_and_complete_project(self):
        repository_root = Path(__file__).resolve().parents[3]
        source_dir = repository_root / "apps/orchestrator/src"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects = root / "projects"
            checkpoint = root / "checkpoints.sqlite"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(source_dir)
            env["LLM_PROVIDER"] = "local"
            env["TTS_PROVIDER"] = "local"
            env["IMAGE_PROVIDER"] = "local"

            def run(*arguments):
                result = subprocess.run(
                    [sys.executable, "-m", "app", *arguments],
                    cwd=repository_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            run(
                "create", "--project-id", "sample_story", "--topic", "River",
                "--duration", "1", "--profile", "simple_story_th",
                "--projects-dir", str(projects),
            )
            first = run(
                "run", "--project-id", "sample_story", "--projects-dir", str(projects),
                "--checkpoint-db", str(checkpoint),
            )
            self.assertEqual(first["status"], "awaiting_script_approval")
            run(
                "approve-script", "--project-id", "sample_story", "--approved",
                "--reviewer", "human", "--projects-dir", str(projects),
                "--checkpoint-db", str(checkpoint),
            )
            final_pause = run(
                "resume", "--project-id", "sample_story", "--projects-dir", str(projects),
                "--checkpoint-db", str(checkpoint), "--tts-words-per-second", "1000",
            )
            self.assertEqual(
                final_pause["status"],
                "awaiting_final_approval",
                final_pause.get("quality_report"),
            )
            run(
                "approve-final", "--project-id", "sample_story", "--approved",
                "--reviewer", "human", "--projects-dir", str(projects),
                "--checkpoint-db", str(checkpoint),
            )
            completed = run(
                "resume", "--project-id", "sample_story", "--projects-dir", str(projects),
                "--checkpoint-db", str(checkpoint),
            )
            self.assertEqual(completed["status"], "completed")

            project = projects / "sample_story"
            for relative in (
                "content/outline.json", "content/script.txt", "scenes/scenes.json",
                "audio/narration.wav", "render/render_payload.json", "render/story.mp4",
                "reports/approvals.json", "reports/quality_report.json",
                "reports/contact_sheet.md", "reports/project_report.md",
            ):
                artifact = project / relative
                self.assertTrue(artifact.is_file(), relative)
                self.assertGreater(artifact.stat().st_size, 0, relative)


if __name__ == "__main__":
    unittest.main()
