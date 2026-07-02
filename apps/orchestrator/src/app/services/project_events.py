from __future__ import annotations

from datetime import UTC, datetime


class ProjectEventStore:
    def __init__(self, limit: int = 200) -> None:
        self._limit = limit
        self._events: dict[str, list[dict[str, object]]] = {}

    def append(
        self,
        project_id: str,
        stage: str,
        scene_id: str | None,
        message: str,
        *,
        level: str = "info",
        **extra: object,
    ) -> None:
        items = self._events.setdefault(project_id, [])
        items.insert(
            0,
            {
                "eventId": f"evt_{len(items) + 1:04d}",
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "stage": stage,
                "sceneId": scene_id,
                "message": message,
                **extra,
            },
        )
        del items[self._limit :]

    def list_events(self, project_id: str) -> list[dict[str, object]]:
        return list(self._events.get(project_id, []))
