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
from app.services.approval_reporting import (
    ApprovalReportingService,
    ApprovalRequest,
    ReportRequest,
)


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
    if args.command == "approve-script":
        return _record_script_approval(args)
    if args.command == "approve-final":
        return _record_final_approval(args)
    if args.command == "report":
        return _write_project_report(args)

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

    approve_script = subparsers.add_parser("approve-script", help="Record script approval")
    _add_approval_arguments(approve_script)

    approve_final = subparsers.add_parser("approve-final", help="Record final publishing approval")
    _add_approval_arguments(approve_final)

    report = subparsers.add_parser("report", help="Write contact sheet and project reports")
    report.add_argument("--project-id", required=True)
    report.add_argument("--projects-dir", default="./projects")
    report.add_argument("--video-path", required=True)
    report.add_argument("--quality-score", required=True, type=float)
    report.add_argument("--issue", action="append", default=[])

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


def _record_script_approval(args: argparse.Namespace) -> int:
    service = ApprovalReportingService(ProjectRepository(Path(args.projects_dir)))
    decision = service.record_script_approval(_approval_request_from_args(args))
    print(json.dumps(decision.to_dict(), ensure_ascii=False))
    return 0


def _record_final_approval(args: argparse.Namespace) -> int:
    service = ApprovalReportingService(ProjectRepository(Path(args.projects_dir)))
    decision = service.record_final_approval(_approval_request_from_args(args))
    print(json.dumps(decision.to_dict(), ensure_ascii=False))
    return 0


def _write_project_report(args: argparse.Namespace) -> int:
    service = ApprovalReportingService(ProjectRepository(Path(args.projects_dir)))
    paths = service.write_project_reports(
        ReportRequest(
            project_id=args.project_id,
            video_path=args.video_path,
            quality_score=args.quality_score,
            issues=args.issue,
        )
    )
    print(json.dumps(paths.to_dict(), ensure_ascii=False))
    return 0


def _add_approval_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--projects-dir", default="./projects")
    approval = parser.add_mutually_exclusive_group(required=True)
    approval.add_argument("--approved", action="store_true")
    approval.add_argument("--changes-requested", action="store_true")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--notes", default="")


def _approval_request_from_args(args: argparse.Namespace) -> ApprovalRequest:
    return ApprovalRequest(
        project_id=args.project_id,
        approved=bool(args.approved),
        reviewer=args.reviewer,
        notes=args.notes,
    )


def _default_checkpoint_db() -> str:
    return os.environ.get("CHECKPOINT_DB", "./data/checkpoints.sqlite")
