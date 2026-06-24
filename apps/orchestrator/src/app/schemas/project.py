from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from app.schemas.state import VideoProjectState


@dataclass(frozen=True)
class CreateProjectRequest:
    topic: str
    target_duration_seconds: int
    profile: str
    target_language: str = "th"

    def __init__(
        self,
        topic: str,
        duration: int | None = None,
        profile: str = "",
        target_duration_seconds: int | None = None,
        target_language: str = "th",
    ):
        normalized_topic = topic.strip()
        if not normalized_topic:
            raise ValueError("topic is required")

        resolved_duration = target_duration_seconds if target_duration_seconds is not None else duration
        if resolved_duration is None or resolved_duration <= 0:
            raise ValueError("duration must be greater than zero")

        if not profile.strip():
            raise ValueError("profile is required")

        object.__setattr__(self, "topic", normalized_topic)
        object.__setattr__(self, "target_duration_seconds", resolved_duration)
        object.__setattr__(self, "profile", profile.strip())
        object.__setattr__(self, "target_language", target_language.strip() or "th")


@dataclass(frozen=True)
class ProjectMetadata:
    project_id: str
    status: str
    created_at: str
    updated_at: str
    topic: str
    target_duration_seconds: int
    target_language: str
    channel_style_profile: str
    current_node: str | None = None

    @classmethod
    def create(cls, project_id: str, request: CreateProjectRequest) -> "ProjectMetadata":
        timestamp = datetime.now(UTC).isoformat()
        return cls(
            project_id=project_id,
            status="created",
            created_at=timestamp,
            updated_at=timestamp,
            topic=request.topic,
            target_duration_seconds=request.target_duration_seconds,
            target_language=request.target_language,
            channel_style_profile=request.profile,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectMetadata":
        return cls(
            project_id=data["project_id"],
            status=data["status"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            topic=data["topic"],
            target_duration_seconds=int(data["target_duration_seconds"]),
            target_language=data["target_language"],
            channel_style_profile=data["channel_style_profile"],
            current_node=data.get("current_node"),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "project_id": self.project_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "topic": self.topic,
            "target_duration_seconds": self.target_duration_seconds,
            "target_language": self.target_language,
            "channel_style_profile": self.channel_style_profile,
        }
        if self.current_node is not None:
            data["current_node"] = self.current_node
        return data

    def to_graph_state(self) -> VideoProjectState:
        return {
            "project_id": self.project_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "topic": self.topic,
            "target_duration_seconds": self.target_duration_seconds,
            "target_language": self.target_language,
            "channel_style_profile": self.channel_style_profile,
            "current_node": self.current_node,
        }

    def with_graph_result(self, state: VideoProjectState) -> "ProjectMetadata":
        return replace(
            self,
            status=state.get("status", self.status),
            updated_at=state.get("updated_at", self.updated_at),
            current_node=state.get("current_node", self.current_node),
        )

    def with_status(self, status: str, current_node: str | None = None) -> "ProjectMetadata":
        return replace(
            self,
            status=status,
            updated_at=datetime.now(UTC).isoformat(),
            current_node=current_node if current_node is not None else self.current_node,
        )
