import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.services.dashboard_control import DashboardActionAdapter, DashboardControlService
from app.services.dashboard_settings import DashboardSettingsService


class _Response:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body
        self.json = json.loads(body.decode("utf-8")) if body else {}


class _ReversibleProtector:
    def protect(self, value: str) -> str:
        return f"enc::{value[::-1]}"

    def unprotect(self, value: str) -> str:
        return value.split("enc::", 1)[1][::-1]


class _NoopSettingsTester:
    def test(self, provider: str):
        return {"ok": True, "provider": provider}


class DashboardWebAcceptanceTests(unittest.TestCase):
    def setUp(self):
        from app.http.dashboard_api import create_dashboard_api_server

        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self.projects = ProjectRepository(root / "projects")
        self.checkpoints = CheckpointRepository(root / "checkpoints.sqlite")
        self.summary_service = DashboardControlService(self.projects, self.checkpoints)
        self.action_adapter = DashboardActionAdapter(self.projects, self.checkpoints)
        self.settings_service = DashboardSettingsService(
            root / "dashboard-settings.json",
            _ReversibleProtector(),
        )
        self.server = create_dashboard_api_server(
            self.summary_service,
            self.action_adapter,
            port=0,
            settings_service=self.settings_service,
            settings_tester=_NoopSettingsTester(),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._temp_dir.cleanup()

    def request(self, method: str, path: str, body=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = {}
        payload = body
        if isinstance(body, dict):
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return _Response(response.status, data)

    def test_settings_then_create_project_without_cli(self):
        settings = self.request("PUT", "/api/settings", {"story_provider": "local"})
        created = self.request(
            "POST",
            "/api/projects",
            {
                "topic": "River",
                "duration": 30,
                "profile": "simple_story_th",
                "targetLanguage": "th",
            },
        )
        listed = self.request("GET", "/api/projects")

        self.assertEqual(settings.status, 200)
        self.assertEqual(created.status, 201)
        self.assertEqual(listed.json["projects"][0]["projectId"], created.json["projectId"])


if __name__ == "__main__":
    unittest.main()
