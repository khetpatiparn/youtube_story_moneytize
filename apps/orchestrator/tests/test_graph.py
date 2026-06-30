import builtins
import importlib.util
import unittest
from unittest.mock import patch


class GraphTests(unittest.TestCase):
    def _assert_graph_initializes_project_state(self, graph):
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

    @unittest.skipUnless(importlib.util.find_spec("langgraph"), "LangGraph is not installed")
    def test_real_langgraph_initializes_project_state(self):
        from app.graph.workflow import build_hello_world_graph

        graph = build_hello_world_graph()
        self._assert_graph_initializes_project_state(graph)

    def test_fallback_graph_initializes_project_state_when_langgraph_is_unavailable(self):
        from app.graph.workflow import SimpleGraph, build_hello_world_graph

        real_import = builtins.__import__

        def import_without_langgraph(name, *args, **kwargs):
            if name == "langgraph.graph":
                raise ModuleNotFoundError("No module named 'langgraph'", name="langgraph")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_langgraph):
            graph = build_hello_world_graph()

        self.assertIsInstance(graph, SimpleGraph)
        self._assert_graph_initializes_project_state(graph)


if __name__ == "__main__":
    unittest.main()
