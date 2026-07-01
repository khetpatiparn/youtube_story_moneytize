import json
import tempfile
import unittest
from pathlib import Path


class _ReversibleProtector:
    def protect(self, value: str) -> str:
        return f"enc::{value[::-1]}"

    def unprotect(self, value: str) -> str:
        prefix = "enc::"
        if not value.startswith(prefix):
            raise ValueError("unexpected protected value")
        return value[len(prefix):][::-1]


class DashboardSettingsServiceTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self._temp_dir.name) / "dashboard-settings.json"

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_settings_response_never_returns_plaintext_key(self):
        from app.services.dashboard_settings import DashboardSettingsService

        service = DashboardSettingsService(self.path, _ReversibleProtector())

        service.update({"gemini_api_key": "AQ.secret", "story_provider": "gemini"})

        self.assertEqual(
            service.public_settings()["gemini_api_key"],
            {"configured": True, "suffix": "cret"},
        )
        self.assertNotIn("AQ.secret", self.path.read_text(encoding="utf-8"))

    def test_remove_secret_clears_configured_state(self):
        from app.services.dashboard_settings import DashboardSettingsService

        service = DashboardSettingsService(self.path, _ReversibleProtector())

        service.update({"gemini_api_key": "AQ.secret"})
        service.update({"gemini_api_key": None})

        self.assertFalse(service.public_settings()["gemini_api_key"]["configured"])

    def test_public_settings_keep_non_secret_values(self):
        from app.services.dashboard_settings import DashboardSettingsService

        service = DashboardSettingsService(self.path, _ReversibleProtector())

        service.update(
            {
                "story_provider": "gemini",
                "image_provider": "cloudflare",
                "projects_dir": "C:/tmp/projects",
                "image_retry_limit": 3,
            }
        )

        self.assertEqual(
            service.public_settings(),
            {
                "story_provider": "gemini",
                "image_provider": "cloudflare",
                "projects_dir": "C:/tmp/projects",
                "image_retry_limit": 3,
                "gemini_api_key": {"configured": False, "suffix": None},
                "cloudflare_account_id": {"configured": False, "suffix": None},
                "cloudflare_api_token": {"configured": False, "suffix": None},
            },
        )

    def test_raw_settings_store_only_encrypted_secret_values(self):
        from app.services.dashboard_settings import DashboardSettingsService

        service = DashboardSettingsService(self.path, _ReversibleProtector())

        service.update(
            {
                "gemini_api_key": "AQ.secret",
                "cloudflare_api_token": "cf-secret",
            }
        )

        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["gemini_api_key"], "enc::terces.QA")
        self.assertEqual(stored["cloudflare_api_token"], "enc::terces-fc")


if __name__ == "__main__":
    unittest.main()
