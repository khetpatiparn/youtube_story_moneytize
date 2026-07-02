from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Sequence

from app.providers.base import PermanentProviderError, ProviderError, RetryableProviderError
from app.http.dashboard_api import serve_dashboard_api
from app.providers.cloudflare_image import (
    DEFAULT_MODEL as DEFAULT_CLOUDFLARE_IMAGE_MODEL,
    CloudflareImageClient,
    CloudflareImageProvider,
    CloudflareRESTImageClient,
)
from app.providers.gemini_story import GeminiStoryProvider, GeminiStoryClient
from app.providers.gemini_tts import GeminiSpeechClient, GeminiTTSProvider, GoogleGenAISpeechClient
from app.repositories.checkpoint_repository import CheckpointRepository
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import CreateProjectRequest
from app.services.approval_reporting import (
    ApprovalReportingService,
    ApprovalRequest,
    ReportRequest,
)
from app.services.dashboard_control import DashboardActionAdapter, DashboardControlService, DashboardJobService
from app.services.dashboard_settings import DashboardSettingsService
from app.services.artifacts import ArtifactStore
from app.services.config import (
    build_image_provider,
    build_story_provider,
    build_tts_provider,
    load_environment,
)
from app.services.image_validation import validate_image_file
from app.services.pipeline_runner import PipelineRunner
from app.services.quality import ffprobe_duration
from app.services.rendering import RemotionRenderer
from app.services.secret_store import WindowsDpapiProtector
from app.services.script_editor import ScriptEditor
from app.services.content_pipeline import validate_story_content
from app.services.job_worker import JobWorker
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
    if args.command == "dashboard-api":
        return _run_dashboard_api(args)
    if args.command == "report":
        return _write_project_report(args)
    if args.command == "smoke-google-tts":
        return _smoke_google_tts(args)
    if args.command == "smoke-google-story":
        return _smoke_google_story(args)
    if args.command == "smoke-cloudflare-image":
        return _smoke_cloudflare_image(args)

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

    dashboard_api = subparsers.add_parser("dashboard-api", help="Run the local dashboard control API")
    dashboard_api.add_argument("--host", default="127.0.0.1")
    dashboard_api.add_argument("--port", type=int, default=8000)
    dashboard_api.add_argument("--projects-dir", default="./projects")
    dashboard_api.add_argument("--checkpoint-db", default=_default_checkpoint_db())

    report = subparsers.add_parser("report", help="Write contact sheet and project reports")
    report.add_argument("--project-id", required=True)
    report.add_argument("--projects-dir", default="./projects")
    report.add_argument("--video-path", required=True)
    report.add_argument("--quality-score", required=True, type=float)
    report.add_argument("--issue", action="append", default=[])

    smoke = subparsers.add_parser("smoke-google-tts", help="Run one intentional Gemini TTS request")
    smoke.add_argument("--text", required=True)
    smoke.add_argument("--output", default="tmp/gemini-tts-smoke.wav")

    story_smoke = subparsers.add_parser(
        "smoke-google-story", help="Run one intentional Gemini story request"
    )
    story_smoke.add_argument("--topic", required=True)
    story_smoke.add_argument("--duration", type=int, required=True)
    story_smoke.add_argument("--profile", required=True)
    story_smoke.add_argument("--output", default="tmp/gemini-story-smoke.json")

    image_smoke = subparsers.add_parser(
        "smoke-cloudflare-image", help="Run one intentional Cloudflare image request"
    )
    image_smoke.add_argument("--prompt", required=True)
    image_smoke.add_argument("--output", default="tmp/cloudflare-image-smoke.jpg")

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
    try:
        result = _build_pipeline_runner(args, configure_content=True).run(args.project_id)
    except (ValueError, ProviderError) as error:
        raise SystemExit(str(error)) from error
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


def _run_dashboard_api(args: argparse.Namespace) -> int:
    from app.http.dashboard_api import serve_dashboard_api
    from app.services.dashboard_control import DashboardActionAdapter, DashboardControlService

    projects = ProjectRepository(Path(args.projects_dir))
    checkpoints = CheckpointRepository(Path(args.checkpoint_db))
    summary_service = DashboardControlService(projects, checkpoints)
    settings_service = DashboardSettingsService(
        _repository_root() / "data" / "dashboard-settings.json",
        WindowsDpapiProtector(),
    )
    settings_tester = DashboardProviderTester(settings_service)
    script_editor = ScriptEditor(projects)

    def runner_factory(project_id: str, *, configure_content: bool) -> PipelineRunner:
        runner_args = SimpleNamespace(
            projects_dir=args.projects_dir,
            checkpoint_db=args.checkpoint_db,
            project_id=project_id,
            max_image_attempts=3,
            tts_words_per_second=2.5,
        )
        return _build_pipeline_runner(runner_args, configure_content=configure_content)

    action_adapter = DashboardActionAdapter(
        projects,
        checkpoints,
        runner_factory=runner_factory,
        approval_service_factory=lambda: ApprovalReportingService(projects, checkpoints),
        summary_service=summary_service,
    )
    jobs = JobRepository(_repository_root() / "data" / "dashboard-jobs.sqlite")
    worker = JobWorker(jobs, action_adapter)
    worker.recover_interrupted_jobs()
    job_service = DashboardJobService(jobs, worker)
    serve_dashboard_api(
        summary_service,
        action_adapter,
        host=args.host,
        port=args.port,
        job_service=job_service,
        script_editor=script_editor,
        settings_service=settings_service,
        settings_tester=settings_tester,
    )
    return 0


class DashboardProviderTester:
    def __init__(self, settings_service: DashboardSettingsService) -> None:
        self.settings_service = settings_service

    def test(self, provider: str) -> dict[str, object]:
        settings = self.settings_service.public_settings()
        if provider == "gemini":
            if not settings["gemini_api_key"]["configured"]:
                raise ValueError("gemini_api_key is not configured")
            return {"ok": True, "provider": "gemini"}
        if provider == "cloudflare":
            missing = [
                field
                for field in ("cloudflare_account_id", "cloudflare_api_token")
                if not settings[field]["configured"]
            ]
            if missing:
                raise ValueError(f"missing Cloudflare settings: {', '.join(missing)}")
            return {"ok": True, "provider": "cloudflare"}
        raise ValueError("provider must be one of: cloudflare, gemini")


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


def _smoke_google_story(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None = None,
    client: GeminiStoryClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    values = os.environ if environ is None else environ
    topic = args.topic.strip() if isinstance(args.topic, str) else ""
    profile = args.profile.strip() if isinstance(args.profile, str) else ""
    if not topic:
        raise SystemExit("Gemini story smoke topic must be nonempty")
    if len(topic) > 500:
        raise SystemExit("Gemini story smoke topic must be at most 500 characters")
    if not isinstance(args.duration, int) or args.duration <= 0:
        raise SystemExit("Gemini story smoke duration must be a positive integer")
    if not profile:
        raise SystemExit("Gemini story smoke profile must be nonempty")
    output = Path(args.output)
    if output.is_absolute() or ".." in output.parts or not output.parts or output.parts[0] != "tmp":
        raise SystemExit("Smoke output must be a relative path under tmp/")
    if output.suffix.lower() != ".json":
        raise SystemExit("Smoke output under tmp/ must use a .json extension")

    api_key = values.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required for Google story smoke testing")
    model = values.get("GEMINI_LLM_MODEL", "gemini-2.5-flash").strip()
    if not model:
        raise SystemExit("GEMINI_LLM_MODEL must not be empty")
    try:
        max_attempts = int(values.get("GEMINI_LLM_MAX_ATTEMPTS", "3"))
        temperature = float(values.get("GEMINI_LLM_TEMPERATURE", "0.7"))
        provider = GeminiStoryProvider(
            api_key=api_key,
            model=model,
            max_attempts=max_attempts,
            temperature=temperature,
            client=client,
            sleep=sleep,
        )
        story = provider.generate_story(topic, args.duration, "th", profile, 1)
        validate_story_content(story)
        output_path = output.as_posix()
        ArtifactStore(_repository_root()).publish_bytes_set(
            {
                output_path: (json.dumps(story, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            }
        )
    except (ValueError, ProviderError) as error:
        raise SystemExit(str(error)) from error

    print(
        json.dumps(
            {
                "model": provider.model,
                "scene_count": len(story["scenes"]),
                "script_characters": len(story["script"]),
                "output_path": output.as_posix(),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _smoke_cloudflare_image(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None = None,
    client: CloudflareImageClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    values = os.environ if environ is None else environ
    prompt = args.prompt.strip() if isinstance(args.prompt, str) else ""
    if not prompt:
        raise SystemExit("Cloudflare image smoke prompt must be nonempty")
    output = Path(args.output)
    if output.is_absolute() or ".." in output.parts or not output.parts or output.parts[0] != "tmp":
        raise SystemExit("Smoke output must be a relative path under tmp/")
    if output.suffix.lower() != ".jpg":
        raise SystemExit("Smoke output under tmp/ must use a .jpg extension")

    account_id = values.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = values.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id:
        raise SystemExit("CLOUDFLARE_ACCOUNT_ID is required for Cloudflare image smoke testing")
    if not api_token:
        raise SystemExit("CLOUDFLARE_API_TOKEN is required for Cloudflare image smoke testing")
    model = values.get("CLOUDFLARE_IMAGE_MODEL", DEFAULT_CLOUDFLARE_IMAGE_MODEL).strip()
    try:
        steps = int(values.get("CLOUDFLARE_IMAGE_STEPS", "4"))
        max_attempts = int(values.get("CLOUDFLARE_IMAGE_MAX_ATTEMPTS", "3"))
        if not 1 <= max_attempts <= 5:
            raise ValueError("CLOUDFLARE_IMAGE_MAX_ATTEMPTS must be between 1 and 5")
        image_client = client or CloudflareRESTImageClient(account_id, api_token)
        provider = CloudflareImageProvider(
            ArtifactStore(_repository_root()), image_client, model=model, steps=steps
        )
    except (TypeError, ValueError) as error:
        raise SystemExit(str(error)) from error

    scene = {
        "scene_id": "cloudflare-image-smoke",
        "title": "Cloudflare image smoke test",
        "prompt": prompt,
        "narration": "",
    }
    for attempt in range(1, max_attempts + 1):
        try:
            result = provider.generate(scene, output.as_posix())
            break
        except RetryableProviderError as error:
            if attempt == max_attempts:
                raise SystemExit("Cloudflare image request failed after retries") from error
            sleep(min(2 ** (attempt - 1), 4))
        except PermanentProviderError as error:
            raise SystemExit("Cloudflare image request failed") from error

    try:
        metadata = validate_image_file(_repository_root() / result["output_path"], "image/jpeg")
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise SystemExit("Cloudflare image smoke output is invalid") from error
    print(
        json.dumps(
            {
                "model": result["model"],
                "seed": result["seed"],
                "steps": result["steps"],
                "width": metadata.width,
                "height": metadata.height,
                "mime_type": metadata.mime_type,
                "output_path": result["output_path"],
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


def _build_pipeline_runner(
    args: argparse.Namespace, *, configure_content: bool = False, project_id: str | None = None
) -> PipelineRunner:
    repository = ProjectRepository(Path(args.projects_dir))
    checkpoints = CheckpointRepository(Path(args.checkpoint_db))
    repository_root = _repository_root()
    resolved_project_id = project_id or args.project_id
    project_dir = repository.project_dir(resolved_project_id)
    renderer = RemotionRenderer(repository_root, project_dir, resolved_project_id)
    checkpoint = checkpoints.load_latest(resolved_project_id)
    needs_external_media = (
        checkpoint is not None and checkpoint.state.get("script_approved") is True
    )
    store = ArtifactStore(project_dir)
    content_provider = build_story_provider(store, os.environ) if configure_content else None
    image_provider = (
        build_image_provider(store, os.environ) if needs_external_media else None
    )
    tts_provider = (
        build_tts_provider(store, os.environ) if needs_external_media else None
    )
    return PipelineRunner(
        repository,
        checkpoints,
        content_provider=content_provider,
        renderer=renderer,
        video_probe=partial(ffprobe_duration, repository_root=repository_root),
        image_provider=image_provider,
        tts_provider=tts_provider,
        max_image_attempts=args.max_image_attempts,
        tts_words_per_second=args.tts_words_per_second,
    )
