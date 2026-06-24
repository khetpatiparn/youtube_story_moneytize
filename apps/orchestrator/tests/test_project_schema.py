import unittest


class ProjectSchemaTests(unittest.TestCase):
    def test_create_project_request_normalizes_input(self):
        from app.schemas.project import CreateProjectRequest

        request = CreateProjectRequest(
            topic="  Thai folktale about courage  ",
            duration=180,
            profile="simple_story_th",
        )

        self.assertEqual(request.topic, "Thai folktale about courage")
        self.assertEqual(request.target_duration_seconds, 180)
        self.assertEqual(request.profile, "simple_story_th")
        self.assertEqual(request.target_language, "th")

    def test_create_project_request_rejects_invalid_values(self):
        from app.schemas.project import CreateProjectRequest

        with self.assertRaises(ValueError):
            CreateProjectRequest(topic="", duration=180, profile="simple_story_th")

        with self.assertRaises(ValueError):
            CreateProjectRequest(topic="Story", duration=0, profile="simple_story_th")

    def test_project_metadata_starts_in_created_state(self):
        from app.schemas.project import CreateProjectRequest, ProjectMetadata

        request = CreateProjectRequest(
            topic="A short story",
            duration=180,
            profile="simple_story_th",
        )

        metadata = ProjectMetadata.create(
            project_id="project_001",
            request=request,
        )

        self.assertEqual(metadata.project_id, "project_001")
        self.assertEqual(metadata.status, "created")
        self.assertEqual(metadata.topic, "A short story")
        self.assertEqual(metadata.target_duration_seconds, 180)
        self.assertEqual(metadata.channel_style_profile, "simple_story_th")
        self.assertIsNotNone(metadata.created_at)
        self.assertIsNotNone(metadata.updated_at)


if __name__ == "__main__":
    unittest.main()
