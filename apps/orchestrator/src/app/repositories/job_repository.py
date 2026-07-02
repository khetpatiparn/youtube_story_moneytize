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
                            preview_image_path, script_excerpt, prompt_excerpt,
                            error_code, error_message, cancel_requested, created_at, updated_at, started_at, finished_at
                        ) values (?, ?, ?, ?, 'queued', 0.0, null, 0, null, null, null, null, null, 0, ?, ?, null, null)
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
                    select progress, stage, preview_image_path, script_excerpt, prompt_excerpt
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
                        preview_image_path = ?,
                        script_excerpt = ?,
                        prompt_excerpt = ?,
                        error_code = ?,
                        error_message = ?,
                        updated_at = ?,
                        finished_at = ?
                    where job_id = ?
                    """,
                    (
                        status,
                        next_progress,
                        next_stage,
                        current[2],
                        current[3],
                        current[4],
                        error_code,
                        error_message,
                        timestamp,
                        timestamp,
                        job_id,
                    ),
                )

        return self.get(job_id)

    def list_jobs(self, project_id: str | None = None) -> list[JobRecord]:
        self._ensure_schema()
        query = """
            select
                job_id, project_id, operation, status, scene_id, progress, stage, attempts,
                preview_image_path, script_excerpt, prompt_excerpt,
                error_code, error_message, cancel_requested, created_at, updated_at, started_at, finished_at
            from jobs
        """
        params: tuple[object, ...] = ()
        if project_id is not None:
            query += " where project_id = ?"
            params = (project_id,)
        query += " order by created_at desc"
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, job_id: str) -> JobRecord:
        self._ensure_schema()
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                """
                select
                    job_id, project_id, operation, status, scene_id, progress, stage, attempts,
                    preview_image_path, script_excerpt, prompt_excerpt,
                    error_code, error_message, cancel_requested, created_at, updated_at, started_at, finished_at
                from jobs
                where job_id = ?
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            raise KeyError(job_id)
        return self._row_to_record(row)

    def request_cancel(self, job_id: str) -> JobRecord:
        self._ensure_schema()
        timestamp = self._now()
        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                current = connection.execute(
                    """
                    select status
                    from jobs
                    where job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(job_id)
                next_status = "cancelling" if current[0] in {"queued", "running"} else current[0]
                connection.execute(
                    """
                    update jobs
                    set cancel_requested = 1,
                        status = ?,
                        updated_at = ?
                    where job_id = ?
                    """,
                    (next_status, timestamp, job_id),
                )
        return self.get(job_id)

    def update_progress(
        self,
        job_id: str,
        *,
        progress: float | None = None,
        stage: str | None = None,
        scene_id: str | None = None,
        preview_image_path: str | None = None,
        script_excerpt: str | None = None,
        prompt_excerpt: str | None = None,
    ) -> JobRecord:
        self._ensure_schema()
        timestamp = self._now()
        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                current = connection.execute(
                    """
                    select progress, stage, scene_id, preview_image_path, script_excerpt, prompt_excerpt
                    from jobs
                    where job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(job_id)
                next_progress = current[0] if progress is None else progress
                next_stage = current[1] if stage is None else stage
                next_scene_id = current[2] if scene_id is None else scene_id
                next_preview_image_path = current[3] if preview_image_path is None else preview_image_path
                next_script_excerpt = current[4] if script_excerpt is None else script_excerpt
                next_prompt_excerpt = current[5] if prompt_excerpt is None else prompt_excerpt
                connection.execute(
                    """
                    update jobs
                    set progress = ?,
                        stage = ?,
                        scene_id = ?,
                        preview_image_path = ?,
                        script_excerpt = ?,
                        prompt_excerpt = ?,
                        updated_at = ?
                    where job_id = ?
                    """,
                    (
                        next_progress,
                        next_stage,
                        next_scene_id,
                        next_preview_image_path,
                        next_script_excerpt,
                        next_prompt_excerpt,
                        timestamp,
                        job_id,
                    ),
                )
        return self.get(job_id)

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
                        preview_image_path text,
                        script_excerpt text,
                        prompt_excerpt text,
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
                columns = {
                    row[1]
                    for row in connection.execute("pragma table_info(jobs)").fetchall()
                }
                if "preview_image_path" not in columns:
                    connection.execute("alter table jobs add column preview_image_path text")
                if "script_excerpt" not in columns:
                    connection.execute("alter table jobs add column script_excerpt text")
                if "prompt_excerpt" not in columns:
                    connection.execute("alter table jobs add column prompt_excerpt text")

    def _row_to_record(self, row: tuple[object, ...]) -> JobRecord:
        return JobRecord(
            job_id=str(row[0]),
            project_id=str(row[1]),
            operation=str(row[2]),
            status=str(row[3]),
            scene_id=None if row[4] is None else str(row[4]),
            progress=float(row[5]),
            stage=None if row[6] is None else str(row[6]),
            preview_image_path=None if row[8] is None else str(row[8]),
            script_excerpt=None if row[9] is None else str(row[9]),
            prompt_excerpt=None if row[10] is None else str(row[10]),
            attempts=int(row[7]),
            error_code=None if row[11] is None else str(row[11]),
            error_message=None if row[12] is None else str(row[12]),
            cancel_requested=bool(row[13]),
            created_at=str(row[14]),
            updated_at=str(row[15]),
            started_at=None if row[16] is None else str(row[16]),
            finished_at=None if row[17] is None else str(row[17]),
        )

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
