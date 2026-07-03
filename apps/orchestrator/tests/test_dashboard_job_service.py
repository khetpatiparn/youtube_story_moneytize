import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.repositories.job_repository import JobRepository
from app.services.dashboard_control import DashboardJobService
from app.services.job_worker import JobWorker


class DashboardJobServiceTests(unittest.TestCase):
    def test_enqueue_wakes_background_worker_and_finishes_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = JobRepository(Path(temp_dir) / "jobs.sqlite")
            actions = MagicMock()
            actions.run_project.return_value = {"currentNode": "script_approval"}
            service = DashboardJobService(jobs, JobWorker(jobs, actions))
            try:
                queued = service.enqueue("project_001", "run")
                deadline = time.monotonic() + 2
                detail = service.get_job(queued["jobId"])
                while detail["status"] not in {"succeeded", "failed", "cancelled"}:
                    if time.monotonic() >= deadline:
                        self.fail(f"job stayed {detail['status']}")
                    time.sleep(0.01)
                    detail = service.get_job(queued["jobId"])

                self.assertEqual(detail["status"], "succeeded")
                actions.run_project.assert_called_once()
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()
