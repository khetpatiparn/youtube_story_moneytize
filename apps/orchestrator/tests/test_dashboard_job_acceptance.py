import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.http.dashboard_api import create_dashboard_api_server
from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository
from app.services.approval_reporting import ApprovalReportingService
from app.services.dashboard_control import (
    DashboardActionAdapter,
    DashboardControlService,
    DashboardJobService,
)
from app.services.job_worker import JobWorker
from app.services.project_events import ProjectEventStore
from app.services.script_editor import ScriptEditor


class _Response:
    def __init__(self, status, body):
        self.status = status
        self.json = json.loads(body.decode("utf-8")) if body else {}


class _AcceptanceRunner:
    def __init__(self, projects, checkpoints, progress_reporter, resume_gate, calls):
        self.projects = projects
        self.checkpoints = checkpoints
        self.progress_reporter = progress_reporter
        self.resume_gate = resume_gate
        self.calls = calls

    def run(self, project_id):
        project_dir = self.projects.project_dir(project_id)
        (project_dir / "content").mkdir(parents=True, exist_ok=True)
        (project_dir / "scenes").mkdir(parents=True, exist_ok=True)
        scenes = [{
            "scene_id": "scene_001",
            "title": "Opening",
            "narration": "A river spirit appeared.",
            "prompt": "River spirit at dawn",
            "motion": "slow_push",
            "focal_point": [0.5, 0.5],
        }]
        (project_dir / "content" / "script.txt").write_text(
            scenes[0]["narration"], encoding="utf-8"
        )
        (project_dir / "scenes" / "scenes.json").write_text(
            json.dumps(scenes, ensure_ascii=False), encoding="utf-8"
        )
        state = {
            **self.projects.load_project(project_id).to_graph_state(),
            "scenes": scenes,
            "script": scenes[0]["narration"],
            "status": "awaiting_script_approval",
            "current_node": "script_approval",
            "waiting_for": "script",
        }
        self._persist(project_id, state)
        self.progress_reporter.stage("script_approval", 0.2)
        return state

    def resume(self, project_id):
        self.calls.append("resume")
        state = dict(self.checkpoints.load_latest(project_id).state)
        if len(self.calls) == 1:
            self.progress_reporter.stage("images", 0.5)
            self.resume_gate.wait(timeout=2)
            self.progress_reporter.stage("render", 0.8)
        state.update({
            "status": "awaiting_final_approval",
            "current_node": "final_approval",
            "waiting_for": "final",
        })
        self._persist(project_id, state)
        return state

    def _persist(self, project_id, state):
        self.checkpoints.save_checkpoint(project_id, state)
        self.projects.save_project(self.projects.load_project(project_id).with_graph_result(state))


class DashboardJobAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.projects = ProjectRepository(root / "projects")
        self.checkpoints = CheckpointRepository(root / "checkpoints.sqlite")
        self.jobs = JobRepository(root / "jobs.sqlite")
        self.events = ProjectEventStore()
        self.resume_gate = threading.Event()
        self.resume_calls = []
        self.summary = DashboardControlService(self.projects, self.checkpoints)

        def runner_factory(project_id, *, configure_content, progress_reporter=None):
            del project_id, configure_content
            return _AcceptanceRunner(
                self.projects,
                self.checkpoints,
                progress_reporter,
                self.resume_gate,
                self.resume_calls,
            )

        self.actions = DashboardActionAdapter(
            self.projects,
            self.checkpoints,
            runner_factory=runner_factory,
            approval_service_factory=lambda: ApprovalReportingService(
                self.projects, self.checkpoints
            ),
            summary_service=self.summary,
        )
        self.script_editor = ScriptEditor(self.projects)
        self._start_runtime()

    def tearDown(self):
        self._stop_runtime()
        self.temp.cleanup()

    def _start_runtime(self):
        self.job_service = DashboardJobService(
            self.jobs, JobWorker(self.jobs, self.actions, events=self.events)
        )
        self.server = create_dashboard_api_server(
            self.summary,
            self.actions,
            port=0,
            job_service=self.job_service,
            script_editor=self.script_editor,
            event_store=self.events,
        )
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def _stop_runtime(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)
        self.job_service.stop()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = {}
        payload = body
        if isinstance(body, dict):
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        result = _Response(response.status, response.read())
        connection.close()
        return result

    def wait_for_job(self, job_id, *statuses):
        deadline = time.monotonic() + 3
        while True:
            detail = self.request("GET", f"/api/jobs/{job_id}").json["job"]
            if detail["status"] in statuses:
                return detail
            if time.monotonic() >= deadline:
                self.fail(f"job stayed {detail['status']}")
            time.sleep(0.01)

    def wait_for_stage(self, job_id, stage):
        deadline = time.monotonic() + 3
        while True:
            detail = self.request("GET", f"/api/jobs/{job_id}").json["job"]
            if detail["stage"] == stage:
                return detail
            if detail["status"] in {"succeeded", "failed", "cancelled"}:
                self.fail(f"job finished as {detail['status']} before stage {stage}")
            if time.monotonic() >= deadline:
                self.fail(f"job never reached stage {stage}")
            time.sleep(0.01)

    def test_browser_control_flow_survives_cancel_and_worker_restart(self):
        created = self.request("POST", "/api/projects", {
            "projectId": "acceptance_story",
            "topic": "River",
            "duration": 30,
            "profile": "simple_story_th",
            "targetLanguage": "th",
        })
        self.assertEqual(created.status, 201)

        run = self.request("POST", "/api/projects/acceptance_story/run")
        first_job = self.wait_for_job(run.json["job"]["jobId"], "succeeded")
        self.assertEqual(first_job["stage"], "script_approval")

        script = self.request("GET", "/api/projects/acceptance_story/script").json
        script["scenes"][0]["narration"] = "The edited river spirit appeared."
        edited = self.request("PUT", "/api/projects/acceptance_story/script", script)
        approved = self.request("POST", "/api/projects/acceptance_story/approve-script", {
            "approved": True,
            "reviewer": "acceptance",
            "revision": edited.json["revision"],
        })
        self.assertEqual(approved.status, 200)

        resume = self.request("POST", "/api/projects/acceptance_story/resume")
        running = self.wait_for_stage(resume.json["job"]["jobId"], "images")
        cancelled = self.request("POST", f"/api/jobs/{running['jobId']}/cancel")
        self.assertEqual(cancelled.status, 200)
        self.resume_gate.set()
        self.wait_for_job(running["jobId"], "cancelled")
        checkpoint_before_restart = self.checkpoints.load_latest("acceptance_story")

        self._stop_runtime()
        self._start_runtime()
        resumed = self.request("POST", "/api/projects/acceptance_story/resume")
        final_job = self.wait_for_job(resumed.json["job"]["jobId"], "succeeded")
        checkpoint_after_restart = self.checkpoints.load_latest("acceptance_story")

        self.assertEqual(final_job["stage"], "final_approval")
        self.assertEqual(checkpoint_before_restart.state["script_approved"], True)
        self.assertEqual(checkpoint_after_restart.state["status"], "awaiting_final_approval")
        self.assertGreaterEqual(len(self.events.list_events("acceptance_story")), 2)


if __name__ == "__main__":
    unittest.main()
