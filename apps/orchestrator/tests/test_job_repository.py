import tempfile
import unittest
from pathlib import Path


class JobRepositoryTests(unittest.TestCase):
    def test_enqueue_blocks_second_active_job_for_same_project(self):
        from app.repositories.job_repository import JobRepository

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = JobRepository(Path(temp_dir) / "jobs.sqlite")

            first = repository.enqueue("project_001", "run")

            with self.assertRaisesRegex(ValueError, "active job"):
                repository.enqueue("project_001", "resume")

            repository.finish(first.job_id, status="succeeded")
            resumed = repository.enqueue("project_001", "resume")

            self.assertEqual(first.status, "queued")
            self.assertEqual(resumed.status, "queued")
            self.assertNotEqual(first.job_id, resumed.job_id)

    def test_claim_next_moves_job_to_running_and_persists_stage(self):
        from app.repositories.job_repository import JobRepository

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = JobRepository(Path(temp_dir) / "jobs.sqlite")
            queued = repository.enqueue("project_001", "run")

            running = repository.claim_next()
            detail = repository.get(queued.job_id)

            self.assertIsNotNone(running)
            self.assertEqual(running.job_id, queued.job_id)
            self.assertEqual(running.status, "running")
            self.assertEqual(detail.status, "running")

    def test_reopen_running_jobs_marks_them_failed_after_restart(self):
        from app.repositories.job_repository import JobRepository

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "jobs.sqlite"
            first = JobRepository(db_path)
            queued = first.enqueue("project_001", "run")
            first.claim_next()

            second = JobRepository(db_path)
            reopened = second.reopen_interrupted_jobs()
            detail = second.get(queued.job_id)

            self.assertEqual([queued.job_id], [job.job_id for job in reopened])
            self.assertEqual(detail.status, "failed")
            self.assertEqual(detail.error_code, "application_restarted")

    def test_update_progress_changes_stage_without_finishing_job(self):
        from app.repositories.job_repository import JobRepository

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = JobRepository(Path(temp_dir) / "jobs.sqlite")
            job = repository.enqueue("project_001", "run")

            updated = repository.update_progress(job.job_id, progress=0.5, stage="images")

            self.assertEqual(updated.status, "queued")
            self.assertEqual(updated.progress, 0.5)
            self.assertEqual(updated.stage, "images")

    def test_cancelling_queued_job_finishes_it_and_releases_project(self):
        from app.repositories.job_repository import JobRepository

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = JobRepository(Path(temp_dir) / "jobs.sqlite")
            queued = repository.enqueue("project_001", "run")

            cancelled = repository.request_cancel(queued.job_id)
            replacement = repository.enqueue("project_001", "resume")

            self.assertEqual(cancelled.status, "cancelled")
            self.assertTrue(cancelled.cancel_requested)
            self.assertIsNotNone(cancelled.finished_at)
            self.assertEqual(replacement.status, "queued")


if __name__ == "__main__":
    unittest.main()
