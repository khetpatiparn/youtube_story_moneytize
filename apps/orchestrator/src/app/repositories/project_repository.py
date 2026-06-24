from __future__ import annotations

import json
import re
from pathlib import Path

from app.schemas.project import CreateProjectRequest, ProjectMetadata

PROJECT_DIRECTORIES = (
    "input",
    "research",
    "outline",
    "script",
    "scenes",
    "prompts",
    "images",
    "audio",
    "render",
    "thumbnail",
    "reports",
    "logs",
)

_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class ProjectRepository:
    def __init__(self, projects_dir: Path):
        self.projects_dir = Path(projects_dir)

    def create_project(
        self,
        request: CreateProjectRequest,
        project_id: str | None = None,
    ) -> ProjectMetadata:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        project_id = project_id or self._next_project_id()
        project_dir = self._project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=False)

        for directory in PROJECT_DIRECTORIES:
            (project_dir / directory).mkdir()

        metadata = ProjectMetadata.create(project_id=project_id, request=request)
        self.save_project(metadata)
        return metadata

    def load_project(self, project_id: str) -> ProjectMetadata:
        project_path = self._project_dir(project_id) / "project.json"
        with project_path.open(encoding="utf-8") as file:
            return ProjectMetadata.from_dict(json.load(file))

    def save_project(self, metadata: ProjectMetadata) -> None:
        project_dir = self._project_dir(metadata.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        project_path = project_dir / "project.json"
        project_path.write_text(
            json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _next_project_id(self) -> str:
        existing_ids = {
            path.name
            for path in self.projects_dir.iterdir()
            if path.is_dir() and path.name.startswith("project_")
        }
        next_number = 1
        while f"project_{next_number:03d}" in existing_ids:
            next_number += 1
        return f"project_{next_number:03d}"

    def _project_dir(self, project_id: str) -> Path:
        if not _PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ValueError("project_id may contain only letters, numbers, '_' and '-'")

        root = self.projects_dir.resolve()
        project_dir = (self.projects_dir / project_id).resolve()
        if root != project_dir and root not in project_dir.parents:
            raise ValueError("project path must stay inside projects_dir")
        return project_dir
