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


class DashboardControlApiTests(unittest.TestCase):
    def setUp(self):
        from app.http.dashboard_api import ProjectActionGate, create_dashboard_api_server

        self.summary_service = _FakeSummaryService()
        self.action_adapter = _FakeActionAdapter()
        self.gate = ProjectActionGate()
        self.server = create_dashboard_api_server(
            self.summary_service,
            self.action_adapter,
            port=0,
            gate=self.gate,
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
