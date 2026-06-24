import unittest


class GraphTests(unittest.TestCase):
    def test_hello_world_graph_initializes_project_state(self):
        from app.graph.workflow import build_hello_world_graph

        graph = build_hello_world_graph()

        result = graph.invoke(
            {
                "project_id": "project_001",
                "topic": "A small kindness becomes a legend",
                "target_duration_seconds": 180,
                "channel_style_profile": "simple_story_th",
            }
        )

        self.assertEqual(result["project_id"], "project_001")
        self.assertEqual(result["status"], "initialized")
        self.assertEqual(result["current_node"], "initialize_project")
        self.assertIn("updated_at", result)


if __name__ == "__main__":
    unittest.main()
