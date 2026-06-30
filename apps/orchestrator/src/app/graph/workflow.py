from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from app.nodes.initialize_project import initialize_project
from app.schemas.state import VideoProjectState


class SimpleGraph:
    """Tiny invoke-compatible graph used before LangGraph is installed."""

    def __init__(self, nodes: Iterable[Callable[[VideoProjectState], VideoProjectState]]):
        self._nodes = tuple(nodes)

    def invoke(self, state: VideoProjectState) -> VideoProjectState:
        current_state = dict(state)
        for node in self._nodes:
            current_state = node(current_state)
        return current_state


def build_hello_world_graph() -> Any:
    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError:
        return SimpleGraph([initialize_project])

    builder = StateGraph(VideoProjectState)
    builder.add_node("initialize_project", initialize_project)
    builder.add_edge(START, "initialize_project")
    builder.add_edge("initialize_project", END)
    return builder.compile()
