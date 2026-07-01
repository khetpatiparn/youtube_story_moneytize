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


class DashboardControlApiTests(unittest.TestCase):
    def setUp(self):
        from app.http.dashboard_api import ProjectActionGate, create_dashboard_api_server

        self.summary_service = _FakeSummaryService()
        self.action_adapter = _FakeActionAdapter()
        self.settings_service = _FakeSettingsService()
        self.settings_tester = _FakeSettingsTester()
        self.gate = ProjectActionGate()
        self.server = create_dashboard_api_server(
            self.summary_service,
            self.action_adapter,
            port=0,
            gate=self.gate,
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

    def test_run_endpoint_invokes_action_adapter(self):
        response = self.request("POST", "/api/projects/project_001/run")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["action"], "run")
        self.assertIn(("run", "project_001"), self.action_adapter.calls)

    def test_resume_endpoint_invokes_action_adapter(self):
        response = self.request("POST", "/api/projects/project_001/resume")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["action"], "resume")
        self.assertIn(("resume", "project_001"), self.action_adapter.calls)

    def test_approve_script_endpoint_validates_and_invokes_action_adapter(self):
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-script",
            {"approved": True, "reviewer": "human"},
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["action"], "approve_script")
        self.assertIn(
            ("approve", "script", "project_001", True, "human"),
            self.action_adapter.calls,
        )

    def test_approve_script_endpoint_defaults_missing_reviewer_to_human(self):
        response = self.request(
            "POST",
            "/api/projects/project_001/approve-script",
            {"approved": True},
        )

        self.assertEqual(response.status, 200)
        self.assertIn(
            ("approve", "script", "project_001", True, "human"),
            self.action_adapter.calls,
        )

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

    def test_unknown_project_returns_not_found(self):
        response = self.request("GET", "/api/projects/project_999")

        self.assertEqual(response.status, 404)

    def test_duplicate_gate_acquire_rejects_second_action(self):
        first = self.gate.acquire("project_001")
        second = self.gate.acquire("project_001")

        self.assertTrue(first)
        self.assertFalse(second)
        self.gate.release("project_001")

    def test_duplicate_in_flight_action_returns_conflict(self):
        self.assertTrue(self.gate.acquire("project_001"))

        response = self.request("POST", "/api/projects/project_001/resume")

        self.assertEqual(response.status, 409)
        self.assertEqual(
            response.json,
            {"ok": False, "error": "Action already running for project_001."},
        )
        self.gate.release("project_001")

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
