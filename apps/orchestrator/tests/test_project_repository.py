import json
import tempfile
import unittest
from pathlib import Path


class ProjectRepositoryTests(unittest.TestCase):
    def test_create_project_writes_metadata_and_expected_directories(self):
        from app.repositories.project_repository import ProjectRepository
        from app.schemas.project import CreateProjectRequest

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ProjectRepository(projects_dir=Path(temp_dir))
            request = CreateProjectRequest(
                topic="A village that learned to share water",
                duration=180,
                profile="simple_story_th",
            )

            metadata = repository.create_project(
                request=request,
                project_id="project_001",
            )

            project_dir = Path(temp_dir) / "project_001"
            self.assertEqual(metadata.project_id, "project_001")
            self.assertTrue((project_dir / "project.json").is_file())

            expected_directories = {
                "input",
                "research",
                "outline",
                "script",
                "scenes",
                "prompts",
                "images",
                "audio",
                "render",
                "thumbnail",
                "reports",
                "logs",
            }
            self.assertEqual(
                expected_directories,
                {path.name for path in project_dir.iterdir() if path.is_dir()},
            )

            project_data = json.loads((project_dir / "project.json").read_text())
            self.assertEqual(project_data["project_id"], "project_001")
            self.assertEqual(project_data["topic"], request.topic)
            self.assertEqual(project_data["status"], "created")


if __name__ == "__main__":
    unittest.main()
