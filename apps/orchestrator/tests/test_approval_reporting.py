import json
import tempfile
import unittest
from pathlib import Path


class ApprovalReportingTests(unittest.TestCase):
    def test_records_approvals_and_writes_static_reports(self):
        from app.repositories.project_repository import ProjectRepository
        from app.schemas.project import CreateProjectRequest
        from app.services.approval_reporting import (
            ApprovalReportingService,
            ApprovalRequest,
            ReportRequest,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ProjectRepository(projects_dir=Path(temp_dir))
            repository.create_project(
                CreateProjectRequest(
                    topic="A village that learned to share water",
                    duration=180,
                    profile="simple_story_th",
                ),
                project_id="project_001",
            )
            project_dir = Path(temp_dir) / "project_001"
            (project_dir / "script" / "script.md").write_text(
                "A village shares water after a dry season.\n",
                encoding="utf-8",
            )
            (project_dir / "scenes" / "scenes.json").write_text(
                json.dumps(
                    [
                        {
                            "scene_id": "scene_001",
                            "image_path": "images/scene_001.png",
                            "prompt": "Village well at sunrise",
                        },
                        {
                            "scene_id": "scene_002",
                            "image_path": "images/scene_002.png",
                            "prompt": "Families sharing water",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            service = ApprovalReportingService(repository)
            script_approval = service.record_script_approval(
                ApprovalRequest(
                    project_id="project_001",
                    approved=True,
                    reviewer="human",
                    notes="Script is ready for scene generation.",
                )
            )
            final_approval = service.record_final_approval(
                ApprovalRequest(
                    project_id="project_001",
                    approved=False,
                    reviewer="human",
                    notes="Needs final audio balance.",
                )
            )
            report_paths = service.write_project_reports(
                ReportRequest(
                    project_id="project_001",
                    video_path="render/story.mp4",
                    quality_score=0.82,
                    issues=["Audio peak is slightly high"],
                )
            )

            self.assertTrue(script_approval.approved)
            self.assertFalse(final_approval.approved)
            self.assertEqual(report_paths.quality_report_path, "reports/quality_report.json")
            self.assertEqual(report_paths.contact_sheet_path, "reports/contact_sheet.md")
            self.assertEqual(report_paths.project_report_path, "reports/project_report.md")

            approvals = json.loads((project_dir / "reports" / "approvals.json").read_text())
            self.assertTrue(approvals["script"]["approved"])
            self.assertFalse(approvals["final"]["approved"])

            quality_report = json.loads((project_dir / "reports" / "quality_report.json").read_text())
            self.assertEqual(quality_report["project_id"], "project_001")
            self.assertEqual(quality_report["video_path"], "render/story.mp4")
            self.assertEqual(quality_report["quality_score"], 0.82)
            self.assertEqual(quality_report["issues"], ["Audio peak is slightly high"])

            contact_sheet = (project_dir / "reports" / "contact_sheet.md").read_text()
            self.assertIn("# Contact Sheet", contact_sheet)
            self.assertIn("scene_001", contact_sheet)
            self.assertIn("images/scene_001.png", contact_sheet)

            project_report = (project_dir / "reports" / "project_report.md").read_text()
            self.assertIn("# Project Report: project_001", project_report)
            self.assertIn("A village that learned to share water", project_report)
            self.assertIn("Script approval: approved", project_report)
            self.assertIn("Final approval: changes requested", project_report)


if __name__ == "__main__":
    unittest.main()
