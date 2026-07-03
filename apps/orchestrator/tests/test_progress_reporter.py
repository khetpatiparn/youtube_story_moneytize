import tempfile
import unittest
from pathlib import Path

from app.repositories.job_repository import JobRepository


class ProgressReporterTests(unittest.TestCase):
    def test_scene_attempt_updates_durable_progress(self):
        from app.services.progress_reporter import ProgressReporter
        from app.services.project_events import ProjectEventStore

        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = JobRepository(Path(temp_dir) / "jobs.sqlite")
            job = jobs.enqueue("project_001", "run")
            reporter = ProgressReporter(jobs, job.job_id, ProjectEventStore())

            reporter.scene(
                "scene_002",
                "image_generating",
                attempt=2,
                progress=0.5,
                prompt_excerpt="Moonlit river spirit close-up",
                script_excerpt="The spirit rose from the water.",
                preview_image_path="projects/project_001/scenes/scene_002.jpg",
            )
            detail = jobs.get(job.job_id)

            self.assertEqual(detail.status, "queued")
            self.assertEqual(detail.progress, 0.5)
            self.assertEqual(detail.scene_id, "scene_002")
            self.assertEqual(detail.stage, "image_generating")
            self.assertEqual(detail.prompt_excerpt, "Moonlit river spirit close-up")
            self.assertEqual(detail.script_excerpt, "The spirit rose from the water.")
            self.assertEqual(detail.preview_image_path, "projects/project_001/scenes/scene_002.jpg")

    def test_stage_updates_progress_and_stage_name(self):
        from app.services.progress_reporter import ProgressReporter
        from app.services.project_events import ProjectEventStore

        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = JobRepository(Path(temp_dir) / "jobs.sqlite")
            job = jobs.enqueue("project_001", "run")
            reporter = ProgressReporter(jobs, job.job_id, ProjectEventStore())

            reporter.stage("images", 0.6)
            detail = jobs.get(job.job_id)

            self.assertEqual(detail.progress, 0.6)
            self.assertEqual(detail.stage, "images")

    def test_progress_reporter_appends_scene_events(self):
        from app.services.progress_reporter import ProgressReporter
        from app.services.project_events import ProjectEventStore

        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = JobRepository(Path(temp_dir) / "jobs.sqlite")
            events = ProjectEventStore()
            job = jobs.enqueue("project_001", "run")
            reporter = ProgressReporter(jobs, job.job_id, events)

            reporter.scene(
                "scene_003",
                "image_generating",
                attempt=1,
                progress=0.25,
                prompt_excerpt="River spirit at dawn",
                script_excerpt="A glow emerged from the river.",
            )

            timeline = events.list_events("project_001")
            self.assertEqual(len(timeline), 1)
            self.assertEqual(timeline[0]["sceneId"], "scene_003")
            self.assertEqual(timeline[0]["stage"], "image_generating")
            self.assertIn("scene_003", timeline[0]["message"])

    def test_stage_stops_when_running_job_has_been_cancelled(self):
        from app.services.progress_reporter import JobCancelledError, ProgressReporter

        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = JobRepository(Path(temp_dir) / "jobs.sqlite")
            job = jobs.enqueue("project_001", "run")
            jobs.claim_next()
            jobs.request_cancel(job.job_id)
            reporter = ProgressReporter(jobs, job.job_id)

            with self.assertRaises(JobCancelledError):
                reporter.stage("images", 0.6)


if __name__ == "__main__":
    unittest.main()
