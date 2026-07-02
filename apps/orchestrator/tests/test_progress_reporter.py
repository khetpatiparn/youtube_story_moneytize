import tempfile
import unittest
from pathlib import Path

from app.repositories.job_repository import JobRepository


class ProgressReporterTests(unittest.TestCase):
    def test_scene_attempt_updates_durable_progress(self):
        from app.services.progress_reporter import ProgressReporter

        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = JobRepository(Path(temp_dir) / "jobs.sqlite")
            job = jobs.enqueue("project_001", "run")
            reporter = ProgressReporter(jobs, job.job_id)

            reporter.scene("scene_002", "generating_image", attempt=2, progress=0.5)
            detail = jobs.get(job.job_id)

            self.assertEqual(detail.status, "queued")
            self.assertEqual(detail.progress, 0.5)
            self.assertEqual(detail.stage, "scene:scene_002:generating_image")

    def test_stage_updates_progress_and_stage_name(self):
        from app.services.progress_reporter import ProgressReporter

        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = JobRepository(Path(temp_dir) / "jobs.sqlite")
            job = jobs.enqueue("project_001", "run")
            reporter = ProgressReporter(jobs, job.job_id)

            reporter.stage("images", 0.6)
            detail = jobs.get(job.job_id)

            self.assertEqual(detail.progress, 0.6)
            self.assertEqual(detail.stage, "images")


if __name__ == "__main__":
    unittest.main()
