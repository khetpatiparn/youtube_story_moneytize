import http.client
import json
import threading
import unittest


class _Response:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body
        self.json = json.loads(body.decode("utf-8")) if body else {}


class _FakeSummaryService:
    def __init__(self):
        self.projects = {
            "project_001": {
                "projectId": "project_001",
                "topic": "A patient river spirit",
                "status": "awaiting_script_approval",
                "currentNode": "script_approval",
                "waitingFor": "script",
                "targetDurationSeconds": 180,
                "targetLanguage": "th",
                "source": "live",
                "availableActions": ["resume", "approve_script"],
            }
        }

    def list_projects(self):
        return list(self.projects.values())

    def get_project(self, project_id: str):
        try:
            return self.projects[project_id]
        except KeyError as error:
            raise KeyError(project_id) from error

    def create_project(self, payload):
        if "admin" in payload:
            raise ValueError("unknown fields: admin")
        created = {
            "projectId": payload.get("projectId", "project_002"),
            "topic": payload["topic"],
            "status": "created",
            "currentNode": None,
            "waitingFor": None,
            "targetDurationSeconds": payload["duration"],
            "targetLanguage": payload.get("targetLanguage", "th"),
            "source": "live",
            "availableActions": ["run"],
        }
        self.projects[created["projectId"]] = created
        return created

    def copy_project(self, project_id: str):
        copied = dict(self.get_project(project_id))
        copied["projectId"] = f"{project_id}_copy"
        copied["status"] = "created"
        copied["currentNode"] = None
        copied["waitingFor"] = None
        copied["availableActions"] = ["run"]
        self.projects[copied["projectId"]] = copied
        return copied

    def delete_project(self, project_id: str, confirm_project_id: str):
        if confirm_project_id != project_id:
            raise ValueError("confirmProjectId must exactly match the project id")
        self.projects.pop(project_id, None)
        return {"ok": True, "projectId": project_id}


class _FakeActionAdapter:
    def __init__(self):
        self.calls = []

    def run_project(self, project_id: str):
        self.calls.append(("run", project_id))
        return {
            "ok": True,
            "projectId": project_id,
            "action": "run",
            "status": "awaiting_script_approval",
            "currentNode": "script_approval",
            "message": "Project started successfully.",
        }

    def resume_project(self, project_id: str):
        self.calls.append(("resume", project_id))
        return {
            "ok": True,
            "projectId": project_id,
            "action": "resume",
            "status": "awaiting_final_approval",
            "currentNode": "final_approval",
            "message": "Project resumed successfully.",
        }

    def approve(self, stage: str, project_id: str, approved: bool, reviewer: str):
        self.calls.append(("approve", stage, project_id, approved, reviewer))
        return {
            "ok": True,
            "projectId": project_id,
            "action": f"approve_{stage}",
            "status": "awaiting_final_approval" if stage == "script" else "completed",
            "currentNode": "final_approval" if stage == "script" else "complete",
            "message": f"{stage} approval recorded.",
        }


class _FakeJobService:
    def __init__(self):
        self.calls = []
        self.jobs = {
            "job_001": {
                "jobId": "job_001",
                "projectId": "project_001",
                "operation": "run",
                "status": "running",
                "progress": 0.5,
                "stage": "images",
                "sceneId": "scene_001",
                "previewImagePath": "projects/project_001/scenes/scene_001.jpg",
                "scriptExcerpt": "The spirit stepped onto the riverbank.",
                "promptExcerpt": "Thai folktale river spirit at sunrise",
                "errorCode": None,
                "errorMessage": None,
                "cancelRequested": False,
            }
        }
        self.project_active_jobs = {"project_001": "job_001"}

    def enqueue(self, project_id: str, operation: str):
        self.calls.append(("enqueue", project_id, operation))
        if project_id in self.project_active_jobs:
            raise ValueError("active job")
        job_id = f"job_{len(self.jobs) + 1:03d}"
        job = {
            "jobId": job_id,
            "projectId": project_id,
            "operation": operation,
            "status": "queued",
            "progress": 0.0,
            "stage": None,
            "sceneId": None,
            "previewImagePath": None,
            "scriptExcerpt": None,
            "promptExcerpt": None,
            "errorCode": None,
            "errorMessage": None,
            "cancelRequested": False,
        }
        self.jobs[job_id] = job
        self.project_active_jobs[project_id] = job_id
        return job

    def list_jobs(self, project_id: str | None = None):
        jobs = list(self.jobs.values())
        if project_id is not None:
            jobs = [job for job in jobs if job["projectId"] == project_id]
            active_id = self.project_active_jobs.get(project_id)
            if active_id is None:
                jobs = [job for job in jobs if job["status"] not in {"queued", "running", "cancelling"}]
        return jobs

    def get_job(self, job_id: str):
        try:
            return self.jobs[job_id]
        except KeyError as error:
            raise KeyError(job_id) from error

    def cancel_job(self, job_id: str):
        job = self.get_job(job_id)
        job["status"] = "cancelling"
        job["cancelRequested"] = True
        self.calls.append(("cancel", job_id))
        return job


class _FakeSettingsService:
    def __init__(self):
        self.values = {
            "story_provider": "local",
            "image_provider": "local",
            "projects_dir": "./projects",
            "image_retry_limit": 3,
            "gemini_api_key": {"configured": False, "suffix": None},
            "cloudflare_account_id": {"configured": False, "suffix": None},
            "cloudflare_api_token": {"configured": False, "suffix": None},
        }
        self.updates = []

    def public_settings(self):
        return dict(self.values)

    def update(self, changes):
        self.updates.append(dict(changes))
        if "gemini_api_key" in changes and changes["gemini_api_key"]:
            self.values["gemini_api_key"] = {"configured": True, "suffix": "cret"}
        for key in ("story_provider", "image_provider", "projects_dir", "image_retry_limit"):
            if key in changes:
                self.values[key] = changes[key]
        return self.public_settings()


class _FakeSettingsTester:
    def __init__(self):
        self.calls = []

    def test(self, provider):
        self.calls.append(provider)
        return {"ok": True, "provider": provider}


class _FakeScriptEditor:
    def __init__(self):
        self.revision = "rev_001"
        self.calls = []
        self.scenes = [
            {"sceneId": "scene_001", "narration": "First narration", "prompt": "First prompt"},
            {"sceneId": "scene_002", "narration": "Second narration", "prompt": "Second prompt"},
        ]

    def read(self, project_id: str):
        self.calls.append(("read", project_id))
        return {"revision": self.revision, "scenes": list(self.scenes)}

    def update(self, project_id: str, revision: str, scenes):
        self.calls.append(("update", project_id, revision, scenes))
        if revision != self.revision:
            raise ValueError("revision")
        self.scenes = list(scenes)
        self.revision = "rev_002"
        return {"revision": self.revision, "scenes": list(self.scenes)}


class _FakeEventStore:
    def __init__(self):
        self.events = {
            "project_001": [
                {
                    "eventId": "evt_001",
                    "timestamp": "2026-07-02T10:30:15Z",
                    "level": "info",
                    "stage": "images",
                    "sceneId": "scene_003",
                    "message": "Image generation started",
                }
            ]
        }

    def list_events(self, project_id: str):
        return list(self.events.get(project_id, []))


class DashboardControlApiTests(unittest.TestCase):
    def setUp(self):
        from app.http.dashboard_api import ProjectActionGate, create_dashboard_api_server

        self.summary_service = _FakeSummaryService()
        self.action_adapter = _FakeActionAdapter()
        self.job_service = _FakeJobService()
        self.settings_service = _FakeSettingsService()
        self.settings_tester = _FakeSettingsTester()
        self.script_editor = _FakeScriptEditor()
        self.event_store = _FakeEventStore()
        self.gate = ProjectActionGate()
        self.server = create_dashboard_api_server(
            self.summary_service,
            self.action_adapter,
            port=0,
            gate=self.gate,
            job_service=self.job_service,
            script_editor=self.script_editor,
            event_store=self.event_store,
            settings_service=self.settings_service,
            settings_tester=self.settings_tester,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method: str, path: str, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        payload = body
        actual_headers = {} if headers is None else dict(headers)
        if isinstance(body, dict):
            payload = json.dumps(body)
            actual_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=payload, headers=actual_headers)
        response = connection.getresponse()
        body_bytes = response.read()
        connection.close()
        return _Response(response.status, body_bytes)

    def test_list_projects_endpoint_returns_projects(self):
        response = self.request("GET", "/api/projects")

        self.assertEqual(response.status, 200)
        self.assertEqual(len(response.json["projects"]), 1)
        self.assertEqual(response.json["projects"][0]["projectId"], "project_001")

    def test_get_project_endpoint_returns_single_project(self):
        response = self.request("GET", "/api/projects/project_001")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["projectId"], "project_001")

    def test_get_script_endpoint_returns_revision_and_scenes(self):
        response = self.request("GET", "/api/projects/project_001/script")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["revision"], "rev_001")
        self.assertEqual(response.json["scenes"][0]["sceneId"], "scene_001")

    def test_get_project_events_returns_recent_timeline(self):
        response = self.request("GET", "/api/projects/project_001/events")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["events"][0]["sceneId"], "scene_003")
        self.assertEqual(response.json["events"][0]["message"], "Image generation started")

    def test_health_endpoint_reports_ready(self):
        response = self.request("GET", "/api/health")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json, {"ok": True})

    def test_get_settings_returns_public_settings_shape(self):
        response = self.request("GET", "/api/settings")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["story_provider"], "local")
        self.assertEqual(response.json["gemini_api_key"], {"configured": False, "suffix": None})

    def test_put_settings_never_echoes_secret(self):
        response = self.request("PUT", "/api/settings", {"gemini_api_key": "AQ.secret"})

        self.assertEqual(response.status, 200)
        self.assertNotIn("AQ.secret", response.body.decode("utf-8"))
        self.assertEqual(response.json["gemini_api_key"], {"configured": True, "suffix": "cret"})

    def test_provider_test_is_never_triggered_by_get_or_put(self):
        self.request("GET", "/api/settings")
        self.request("PUT", "/api/settings", {"story_provider": "local"})

        self.assertEqual(self.settings_tester.calls, [])

    def test_post_settings_test_runs_only_explicit_provider_probe(self):
        response = self.request("POST", "/api/settings/test", {"provider": "gemini"})

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json, {"ok": True, "provider": "gemini"})
        self.assertEqual(self.settings_tester.calls, ["gemini"])

    def test_create_project_endpoint_returns_created_summary(self):
        response = self.request(
            "POST",
            "/api/projects",
            {"topic": "River spirit", "duration": 60, "profile": "simple_story_th", "targetLanguage": "th"},
        )

        self.assertEqual(response.status, 201)
        self.assertEqual(response.json["status"], "created")
        self.assertEqual(response.json["availableActions"], ["run"])

    def test_create_project_rejects_unknown_field(self):
        response = self.request(
            "POST",
            "/api/projects",
            {"topic": "x", "duration": 60, "profile": "simple_story_th", "admin": True},
        )

        self.assertEqual(response.status, 400)

    def test_copy_then_delete_requires_exact_confirmation(self):
        copied = self.request("POST", "/api/projects/project_001/copy", {})
        denied = self.request(
            "DELETE",
            f"/api/projects/{copied.json['projectId']}",
            {"confirmProjectId": "wrong"},
        )

        self.assertEqual(copied.status, 201)
        self.assertEqual(denied.status, 400)

    def test_run_endpoint_returns_accepted_job(self):
        response = self.request("POST", "/api/projects/project_001/run")

        self.assertEqual(response.status, 409)
        self.assertEqual(response.json["job"]["jobId"], "job_001")

    def test_resume_endpoint_returns_accepted_job_when_no_duplicate_exists(self):
        self.job_service.project_active_jobs.pop("project_001", None)
        response = self.request("POST", "/api/projects/project_001/resume")

        self.assertEqual(response.status, 202)
        self.assertEqual(response.json["job"]["operation"], "resume")
        self.assertIn(("enqueue", "project_001", "resume"), self.job_service.calls)

    def test_list_jobs_endpoint_filters_by_project(self):
        response = self.request("GET", "/api/jobs?projectId=project_001")

        self.assertEqual(response.status, 200)
        self.assertEqual(len(response.json["jobs"]), 1)
        self.assertEqual(response.json["jobs"][0]["jobId"], "job_001")

    def test_get_job_endpoint_returns_single_job(self):
        response = self.request("GET", "/api/jobs/job_001")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["job"]["status"], "running")
        self.assertEqual(response.json["job"]["sceneId"], "scene_001")
        self.assertEqual(response.json["job"]["previewImagePath"], "projects/project_001/scenes/scene_001.jpg")
        self.assertEqual(response.json["job"]["scriptExcerpt"], "The spirit stepped onto the riverbank.")
        self.assertEqual(response.json["job"]["promptExcerpt"], "Thai folktale river spirit at sunrise")

    def test_cancel_job_endpoint_marks_job_cancelling(self):
        response = self.request("POST", "/api/jobs/job_001/cancel")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["job"]["status"], "cancelling")
        self.assertTrue(response.json["job"]["cancelRequested"])

    def test_put_script_endpoint_updates_revision_and_scenes(self):
        self.job_service.project_active_jobs.pop("project_001", None)
        response = self.request(
            "PUT",
            "/api/projects/project_001/script",
            {
                "revision": "rev_001",
                "scenes": [
                    {"sceneId": "scene_001", "narration": "Updated first", "prompt": "Updated prompt"},
                    {"sceneId": "scene_002", "narration": "Updated second", "prompt": "Updated prompt 2"},
                ],
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["revision"], "rev_002")
        self.assertEqual(response.json["scenes"][0]["narration"], "Updated first")

    def test_put_script_rejects_stale_revision(self):
        self.job_service.project_active_jobs.pop("project_001", None)
        response = self.request(
            "PUT",
            "/api/projects/project_001/script",
            {
                "revision": "old",
                "scenes": [{"sceneId": "scene_001", "narration": "Updated", "prompt": "Updated"}],
            },
        )

        self.assertEqual(response.status, 400)

    def test_put_script_rejects_active_project_job(self):
        response = self.request(
            "PUT",
            "/api/projects/project_001/script",
            {
                "revision": "rev_001",
                "scenes": [{"sceneId": "scene_001", "narration": "Updated", "prompt": "Updated"}],
            },
        )

        self.assertEqual(response.status, 409)
        self.assertEqual(response.json["job"]["jobId"], "job_001")

    def test_unknown_job_returns_not_found(self):
        response = self.request("GET", "/api/jobs/job_999")

        self.assertEqual(response.status, 404)

    def test_approve_script_endpoint_validates_and_invokes_action_adapter(self):
        self.job_service.project_active_jobs.pop("project_001", None)
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-script",
            {"approved": True, "reviewer": "human", "revision": "rev_001"},
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["action"], "approve_script")
        self.assertIn(
            ("approve", "script", "project_001", True, "human"),
            self.action_adapter.calls,
        )

    def test_approve_script_endpoint_defaults_missing_reviewer_to_human(self):
        self.job_service.project_active_jobs.pop("project_001", None)
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-script",
            {"approved": True, "revision": "rev_001"},
        )

        self.assertEqual(response.status, 200)
        self.assertIn(
            ("approve", "script", "project_001", True, "human"),
            self.action_adapter.calls,
        )

    def test_approve_script_endpoint_requires_current_revision(self):
        self.job_service.project_active_jobs.pop("project_001", None)
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-script",
            {"approved": True, "reviewer": "human", "revision": "stale"},
        )

        self.assertEqual(response.status, 409)

    def test_approve_final_endpoint_validates_and_invokes_action_adapter(self):
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-final",
            {"approved": False, "reviewer": "human"},
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["action"], "approve_final")
        self.assertIn(
            ("approve", "final", "project_001", False, "human"),
            self.action_adapter.calls,
        )

    def test_invalid_json_returns_bad_request(self):
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-script",
            "{invalid",
            {"Content-Type": "application/json"},
        )

        self.assertEqual(response.status, 400)

    def test_put_settings_requires_application_json(self):
        response = self.request("PUT", "/api/settings", "{}", {"Content-Type": "text/plain"})

        self.assertEqual(response.status, 400)

    def test_delete_project_requires_application_json(self):
        response = self.request("DELETE", "/api/projects/project_001", "{}", {"Content-Type": "text/plain"})

        self.assertEqual(response.status, 400)

    def test_unknown_project_returns_not_found(self):
        response = self.request("GET", "/api/projects/project_999")

        self.assertEqual(response.status, 404)

    def test_duplicate_gate_acquire_rejects_second_action(self):
        first = self.gate.acquire("project_001")
        second = self.gate.acquire("project_001")

        self.assertTrue(first)
        self.assertFalse(second)
        self.gate.release("project_001")

    def test_duplicate_project_mutation_returns_conflict_with_active_job(self):
        response = self.request("POST", "/api/projects/project_001/resume")

        self.assertEqual(response.status, 409)
        self.assertEqual(response.json["job"]["jobId"], "job_001")

    def test_approval_body_requires_boolean_approved(self):
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-script",
            {"approved": "yes", "reviewer": "human"},
        )

        self.assertEqual(response.status, 400)

    def test_approval_body_requires_bounded_reviewer(self):
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-script",
            {"approved": True, "reviewer": "x" * 65},
        )

        self.assertEqual(response.status, 400)

    def test_server_binds_to_localhost_by_default(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
