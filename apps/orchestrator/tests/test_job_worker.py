import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.repositories.job_repository import JobRepository


class JobWorkerTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "jobs.sqlite"
        self.jobs = JobRepository(self.db_path)
        self.actions = MagicMock()

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_worker_returns_immediately_and_records_result(self):
        from app.services.job_worker import JobWorker

        self.actions.run_project.return_value = {"currentNode": "script_approval"}
        worker = JobWorker(self.jobs, self.actions, secret_values=lambda: [])
        job = self.jobs.enqueue("project_001", "run")

        processed = worker.process_one()
        detail = self.jobs.get(job.job_id)

        self.assertTrue(processed)
        self.actions.run_project.assert_called_once_with("project_001")
        self.assertEqual(detail.status, "succeeded")
        self.assertEqual(detail.progress, 1.0)
        self.assertEqual(detail.stage, "script_approval")

    def test_provider_failure_redacts_secret(self):
        from app.services.job_worker import JobWorker

        self.actions.run_project.side_effect = RuntimeError("token AQ.secret failed")
        worker = JobWorker(self.jobs, self.actions, secret_values=lambda: ["AQ.secret"])
        job = self.jobs.enqueue("project_001", "run")

        worker.process_one()
        detail = self.jobs.get(job.job_id)

        self.assertEqual(detail.status, "failed")
        self.assertNotIn("AQ.secret", detail.error_message)
        self.assertEqual(detail.error_code, "runtime_error")

    def test_process_one_returns_false_when_queue_is_empty(self):
        from app.services.job_worker import JobWorker

        worker = JobWorker(self.jobs, self.actions, secret_values=lambda: [])

        self.assertFalse(worker.process_one())

    def test_recover_interrupted_jobs_marks_running_jobs_failed(self):
        from app.services.job_worker import JobWorker

        queued = self.jobs.enqueue("project_001", "run")
        self.jobs.claim_next()
        worker = JobWorker(self.jobs, self.actions, secret_values=lambda: [])

        reopened = worker.recover_interrupted_jobs()
        detail = self.jobs.get(queued.job_id)

        self.assertEqual([queued.job_id], [job.job_id for job in reopened])
        self.assertEqual(detail.status, "failed")
        self.assertEqual(detail.error_code, "application_restarted")


if __name__ == "__main__":
    unittest.main()
