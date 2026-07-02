from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.job import JobRecord

ACTIVE_JOB_STATUSES = ("queued", "running", "cancelling")


class JobRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def enqueue(self, project_id: str, operation: str, scene_id: str | None = None) -> JobRecord:
        self._ensure_schema()
        timestamp = self._now()
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                with connection:
                    connection.execute(
                        """
                        insert into jobs (
                            job_id, project_id, operation, scene_id, status, progress, stage, attempts,
                            error_code, error_message, cancel_requested, created_at, updated_at, started_at, finished_at
                        ) values (?, ?, ?, ?, 'queued', 0.0, null, 0, null, null, 0, ?, ?, null, null)
                        """,
                        (job_id, project_id, operation, scene_id, timestamp, timestamp),
                    )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"active job already exists for project {project_id}") from error

        return self.get(job_id)

    def claim_next(self) -> JobRecord | None:
        self._ensure_schema()
        timestamp = self._now()
        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                row = connection.execute(
                    """
                    select job_id
                    from jobs
                    where status = 'queued'
                    order by created_at asc
                    limit 1
                    """
                ).fetchone()
                if row is None:
                    return None

                connection.execute(
                    """
                    update jobs
                    set status = 'running',
                        started_at = coalesce(started_at, ?),
                        updated_at = ?
                    where job_id = ?
                    """,
                    (timestamp, timestamp, row[0]),
                )

        return self.get(row[0])

    def finish(
        self,
        job_id: str,
        status: str,
        *,
        progress: float | None = None,
        stage: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> JobRecord:
        self._ensure_schema()
        timestamp = self._now()
        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                current = connection.execute(
                    """
                    select progress, stage
                    from jobs
                    where job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(job_id)

                next_progress = current[0] if progress is None else progress
                next_stage = current[1] if stage is None else stage
                connection.execute(
                    """
                    update jobs
                    set status = ?,
                        progress = ?,
                        stage = ?,
                        error_code = ?,
                        error_message = ?,
                        updated_at = ?,
                        finished_at = ?
                    where job_id = ?
                    """,
                    (status, next_progress, next_stage, error_code, error_message, timestamp, timestamp, job_id),
                )

        return self.get(job_id)

    def get(self, job_id: str) -> JobRecord:
        self._ensure_schema()
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                """
                select
                    job_id, project_id, operation, status, scene_id, progress, stage, attempts,
                    error_code, error_message, cancel_requested, created_at, updated_at, started_at, finished_at
                from jobs
                where job_id = ?
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            raise KeyError(job_id)
        return self._row_to_record(row)

    def reopen_interrupted_jobs(self) -> list[JobRecord]:
        self._ensure_schema()
        timestamp = self._now()
        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                rows = connection.execute(
                    """
                    select job_id
                    from jobs
                    where status = 'running'
                    order by created_at asc
                    """
                ).fetchall()
                connection.execute(
                    """
                    update jobs
                    set status = 'failed',
                        error_code = 'application_restarted',
                        error_message = 'application restarted during job execution',
                        updated_at = ?,
                        finished_at = ?
                    where status = 'running'
                    """,
                    (timestamp, timestamp),
                )

        return [self.get(row[0]) for row in rows]

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                connection.execute(
                    """
                    create table if not exists jobs (
                        job_id text primary key,
                        project_id text not null,
                        operation text not null,
                        scene_id text,
                        status text not null,
                        progress real not null,
                        stage text,
                        attempts integer not null,
                        error_code text,
                        error_message text,
                        cancel_requested integer not null default 0,
                        created_at text not null,
                        updated_at text not null,
                        started_at text,
                        finished_at text
                    )
                    """
                )
                connection.execute(
                    """
                    create unique index if not exists jobs_one_active_per_project
                    on jobs(project_id)
                    where status in ('queued', 'running', 'cancelling')
                    """
                )

    def _row_to_record(self, row: tuple[object, ...]) -> JobRecord:
        return JobRecord(
            job_id=str(row[0]),
            project_id=str(row[1]),
            operation=str(row[2]),
            status=str(row[3]),
            scene_id=None if row[4] is None else str(row[4]),
            progress=float(row[5]),
            stage=None if row[6] is None else str(row[6]),
            attempts=int(row[7]),
            error_code=None if row[8] is None else str(row[8]),
            error_message=None if row[9] is None else str(row[9]),
            cancel_requested=bool(row[10]),
            created_at=str(row[11]),
            updated_at=str(row[12]),
            started_at=None if row[13] is None else str(row[13]),
            finished_at=None if row[14] is None else str(row[14]),
        )

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
