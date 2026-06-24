from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from app.graph.workflow import build_hello_world_graph
from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import CreateProjectRequest


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "create":
        return _create_project(args)
    if args.command == "status":
        return _show_status(args)
    if args.command == "run":
        return _run_project(args)
    if args.command == "resume":
        return _resume_project(args)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app")
    subparsers = parser.add_subparsers(dest="command")

    create = subparsers.add_parser("create", help="Create a new video project")
    create.add_argument("--topic", required=True)
    create.add_argument("--duration", type=int, required=True)
    create.add_argument("--profile", required=True)
    create.add_argument("--project-id")
    create.add_argument("--projects-dir", default="./projects")

    status = subparsers.add_parser("status", help="Show project status")
    status.add_argument("--project-id", required=True)
    status.add_argument("--projects-dir", default="./projects")

    run = subparsers.add_parser("run", help="Run the hello-world graph")
    run.add_argument("--project-id", required=True)
    run.add_argument("--projects-dir", default="./projects")
    run.add_argument("--checkpoint-db", default=_default_checkpoint_db())

    resume = subparsers.add_parser("resume", help="Resume project state from checkpoint")
    resume.add_argument("--project-id", required=True)
    resume.add_argument("--projects-dir", default="./projects")
    resume.add_argument("--checkpoint-db", default=_default_checkpoint_db())

    return parser


def _create_project(args: argparse.Namespace) -> int:
    repository = ProjectRepository(Path(args.projects_dir))
    request = CreateProjectRequest(
        topic=args.topic,
        duration=args.duration,
        profile=args.profile,
    )
    metadata = repository.create_project(request, project_id=args.project_id)
    print(json.dumps(metadata.to_dict(), ensure_ascii=False))
    return 0


def _show_status(args: argparse.Namespace) -> int:
    repository = ProjectRepository(Path(args.projects_dir))
    metadata = repository.load_project(args.project_id)
    print(json.dumps(metadata.to_dict(), ensure_ascii=False))
    return 0


def _run_project(args: argparse.Namespace) -> int:
    repository = ProjectRepository(Path(args.projects_dir))
    checkpoints = CheckpointRepository(Path(args.checkpoint_db))
    metadata = repository.load_project(args.project_id)
    graph = build_hello_world_graph()
    result = graph.invoke(metadata.to_graph_state())
    checkpoints.save_checkpoint(args.project_id, result)
    metadata = metadata.with_graph_result(result)
    repository.save_project(metadata)
    print(json.dumps(metadata.to_dict(), ensure_ascii=False))
    return 0


def _resume_project(args: argparse.Namespace) -> int:
    repository = ProjectRepository(Path(args.projects_dir))
    checkpoints = CheckpointRepository(Path(args.checkpoint_db))
    checkpoint = checkpoints.load_latest(args.project_id)
    if checkpoint is None:
        raise SystemExit(f"No checkpoint found for project_id {args.project_id}")

    metadata = repository.load_project(args.project_id)
    metadata = metadata.with_graph_result(checkpoint.state)
    repository.save_project(metadata)
    print(json.dumps(metadata.to_dict(), ensure_ascii=False))
    return 0


def _default_checkpoint_db() -> str:
    return os.environ.get("CHECKPOINT_DB", "./data/checkpoints.sqlite")
