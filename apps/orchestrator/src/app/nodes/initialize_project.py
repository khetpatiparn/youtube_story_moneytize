from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.state import VideoProjectState


def initialize_project(state: VideoProjectState) -> VideoProjectState:
    next_state = dict(state)
    next_state["status"] = "initialized"
    next_state["current_node"] = "initialize_project"
    next_state["updated_at"] = datetime.now(UTC).isoformat()
    return next_state
