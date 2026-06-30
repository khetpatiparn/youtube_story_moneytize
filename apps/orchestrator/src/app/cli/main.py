from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Sequence

from app.providers.base import ProviderError
from app.providers.gemini_tts import GeminiSpeechClient, GeminiTTSProvider, GoogleGenAISpeechClient
from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import CreateProjectRequest
from app.services.approval_reporting import (
    ApprovalReportingService,
    ApprovalRequest,
    ReportRequest,
)
from app.services.artifacts import ArtifactStore
from app.services.config import build_image_provider, build_tts_provider, load_environment
from app.services.pipeline_runner import PipelineRunner
from app.services.quality import ffprobe_duration
from app.services.rendering import RemotionRenderer
from app.services.timeline import wav_metadata


def main(argv: Sequence[str] | None = None) -> int:
    load_environment(_repository_root())
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
    if args.command == "smoke-google-tts":
        return _smoke_google_tts(args)

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

    run = subparsers.add_parser("run", help="Run the content pipeline")
    run.add_argument("--project-id", required=True)
    run.add_argument("--projects-dir", default="./projects")
    run.add_argument("--checkpoint-db", default=_default_checkpoint_db())
    run.add_argument("--max-image-attempts", type=int, default=3)
    run.add_argument("--tts-words-per-second", type=float, default=2.5)

    resume = subparsers.add_parser("resume", help="Resume project state from checkpoint")
    resume.add_argument("--project-id", required=True)
    resume.add_argument("--projects-dir", default="./projects")
    resume.add_argument("--checkpoint-db", default=_default_checkpoint_db())
    resume.add_argument("--max-image-attempts", type=int, default=3)
    resume.add_argument("--tts-words-per-second", type=float, default=2.5)

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

    smoke = subparsers.add_parser("smoke-google-tts", help="Run one intentional Gemini TTS request")
    smoke.add_argument("--text", required=True)
    smoke.add_argument("--output", default="tmp/gemini-tts-smoke.wav")

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
    result = _build_pipeline_runner(args).run(args.project_id)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _resume_project(args: argparse.Namespace) -> int:
    try:
        result = _build_pipeline_runner(args).resume(args.project_id)
    except (ValueError, ProviderError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _record_script_approval(args: argparse.Namespace) -> int:
    service = ApprovalReportingService(
        ProjectRepository(Path(args.projects_dir)),
        CheckpointRepository(Path(args.checkpoint_db)),
    )
    decision = service.record_script_approval(_approval_request_from_args(args))
    print(json.dumps(decision.to_dict(), ensure_ascii=False))
    return 0


def _record_final_approval(args: argparse.Namespace) -> int:
    service = ApprovalReportingService(
        ProjectRepository(Path(args.projects_dir)),
        CheckpointRepository(Path(args.checkpoint_db)),
    )
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


def _smoke_google_tts(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None = None,
    client: GeminiSpeechClient | None = None,
) -> int:
    values = os.environ if environ is None else environ
    output = Path(args.output)
    if output.is_absolute() or ".." in output.parts or not output.parts or output.parts[0] != "tmp":
        raise SystemExit("Smoke output must be a relative path under tmp/")
    if output.suffix.lower() != ".wav":
        raise SystemExit("Smoke output under tmp/ must use a .wav extension")
    api_key = values.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required for Google TTS smoke testing")
    model = values.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview").strip()
    voice = values.get("GEMINI_TTS_VOICE", "Charon").strip()
    try:
        max_attempts = int(values.get("GEMINI_TTS_MAX_ATTEMPTS", "3"))
        speech_client = client or GoogleGenAISpeechClient(api_key)
        provider = GeminiTTSProvider(
            ArtifactStore(_repository_root()),
            api_key=api_key,
            model=model,
            voice=voice,
            max_attempts=max_attempts,
            client=speech_client,
        )
        result = asyncio.run(provider.synthesize(args.text, voice, output.as_posix(), {}))
        metadata = wav_metadata(_repository_root() / result.output_path, allowed_sample_rates=(24000,))
    except (ValueError, ProviderError) as error:
        raise SystemExit(str(error)) from error
    print(
        json.dumps(
            {
                "model": result.model,
                "voice": result.voice_id,
                "sample_rate": metadata.sample_rate,
                "duration_seconds": metadata.duration_seconds,
                "output_path": result.output_path,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _add_approval_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--projects-dir", default="./projects")
    parser.add_argument("--checkpoint-db", default=_default_checkpoint_db())
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


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _build_pipeline_runner(args: argparse.Namespace) -> PipelineRunner:
    repository = ProjectRepository(Path(args.projects_dir))
    checkpoints = CheckpointRepository(Path(args.checkpoint_db))
    repository_root = _repository_root()
    project_dir = repository.project_dir(args.project_id)
    renderer = RemotionRenderer(repository_root, project_dir, args.project_id)
    checkpoint = checkpoints.load_latest(args.project_id)
    needs_external_media = (
        checkpoint is not None and checkpoint.state.get("script_approved") is True
    )
    store = ArtifactStore(project_dir)
    image_provider = (
        build_image_provider(store, os.environ) if needs_external_media else None
    )
    tts_provider = (
        build_tts_provider(store, os.environ) if needs_external_media else None
    )
    return PipelineRunner(
        repository,
        checkpoints,
        renderer=renderer,
        video_probe=partial(ffprobe_duration, repository_root=repository_root),
        image_provider=image_provider,
        tts_provider=tts_provider,
        max_image_attempts=args.max_image_attempts,
        tts_words_per_second=args.tts_words_per_second,
    )
