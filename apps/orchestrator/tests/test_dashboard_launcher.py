import unittest
from pathlib import Path


class DashboardLauncherTests(unittest.TestCase):
    def test_launcher_uses_loopback_and_health_check(self):
        script = Path("scripts/start-dashboard.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("127.0.0.1", script)
        self.assertIn("/api/health", script)
        self.assertIn("Start-Process", script)
        self.assertIn("--strictPort", script)
        self.assertNotIn("0.0.0.0", script)

    def test_launcher_exports_pythonpath_for_dashboard_api(self):
        script = Path("scripts/start-dashboard.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("PYTHONPATH", script)
        self.assertIn("apps/orchestrator/src", script.replace("\\", "/"))

    def test_launcher_falls_back_to_system_python_when_venv_is_missing(self):
        script = Path("scripts/start-dashboard.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("Get-Command python", script)
        self.assertIn("Missing Python interpreter", script)

    def test_launcher_reuses_healthy_existing_ports_before_starting_new_processes(self):
        script = Path("scripts/start-dashboard.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("Test-TcpPortInUse", script)
        self.assertIn("API port 8000 is already in use", script)
        self.assertIn("Dashboard port 5173 is already in use", script)


if __name__ == "__main__":
    unittest.main()
