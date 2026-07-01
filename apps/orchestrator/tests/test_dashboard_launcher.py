import unittest
from pathlib import Path


class DashboardLauncherTests(unittest.TestCase):
    def test_launcher_uses_loopback_and_health_check(self):
        script = Path("scripts/start-dashboard.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("127.0.0.1", script)
        self.assertIn("/api/health", script)
        self.assertIn("Start-Process", script)
        self.assertNotIn("0.0.0.0", script)


if __name__ == "__main__":
    unittest.main()
