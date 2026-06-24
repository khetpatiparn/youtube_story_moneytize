from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schemas.state import VideoProjectState


@dataclass(frozen=True)
class CheckpointRecord:
    thread_id: str
    state: VideoProjectState
    updated_at: str


class CheckpointRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def save_checkpoint(
        self,
        thread_id: str,
        state: VideoProjectState,
    ) -> CheckpointRecord:
        self._ensure_schema()
        updated_at = datetime.now(UTC).isoformat()
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True)

        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                connection.execute(
                    """
                    insert into checkpoints (thread_id, state_json, updated_at)
                    values (?, ?, ?)
                    on conflict(thread_id) do update set
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (thread_id, payload, updated_at),
                )

        return CheckpointRecord(thread_id=thread_id, state=dict(state), updated_at=updated_at)

    def load_latest(self, thread_id: str) -> CheckpointRecord | None:
        self._ensure_schema()
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                """
                select thread_id, state_json, updated_at
                from checkpoints
                where thread_id = ?
                """,
                (thread_id,),
            ).fetchone()

        if row is None:
            return None

        return CheckpointRecord(
            thread_id=row[0],
            state=json.loads(row[1]),
            updated_at=row[2],
        )

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                connection.execute(
                    """
                    create table if not exists checkpoints (
                        thread_id text primary key,
                        state_json text not null,
                        updated_at text not null
                    )
                    """
                )
