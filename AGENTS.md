# Repository Guidelines

## Project Structure & Module Organization
This repo contains `youtube_story_automation_poc_plan.md`, Python orchestrator, static approval/reporting artifacts, and Remotion renderer.

- `apps/orchestrator/src/` for graph, nodes, schemas, providers, services, repositories, and CLI.
- `apps/orchestrator/tests/` for Python tests.
- `apps/renderer/src/` for Remotion compositions, components, motions, and `index.tsx`.
- `apps/dashboard/` for the local read-only Media QA web dashboard.
- `configs/` for prompts, channel profiles, and render profiles.
- `projects/{project_id}/` for generated assets, approvals, reports, logs, and renders.
- `data/` for checkpoints and caches.

## Build, Test, and Development Commands
Use `$env:PYTHONPATH='apps/orchestrator/src'` unless installed editable.
- `python -m unittest discover apps/orchestrator/tests` runs orchestrator tests.
- `python -m unittest apps/orchestrator/tests/test_end_to_end.py` runs the real local CLI-to-MP4 acceptance test.
- `python -m app create --topic "..." --duration 180 --profile simple_story_th` creates a project.
- `python -m app run --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite` runs and checkpoints.
- `python -m app resume --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite` restores checkpoint state.
- `python -m app status --project-id project_001` inspects progress.
- `python -m app approve-script --project-id project_001 --approved --reviewer human` records approval.
- `python -m app approve-final --project-id project_001 --changes-requested --reviewer human` records final review.
- `python -m app report --project-id project_001 --video-path render/story.mp4 --quality-score 0.91` writes reports.
- `python -m app smoke-google-tts --text "..." --output tmp/gemini-tts-smoke.wav` makes one intentional live Gemini TTS request.
- `npm.cmd run test:renderer` validates static renderer payloads.
- `npm.cmd run render:sample` renders `renders/sample.mp4`.
- `npm.cmd run test:dashboard` validates dashboard data loading and UI contracts.
- `npm.cmd run prepare:dashboard-data` exports project/report data for the browser dashboard.
- `npm.cmd run dev:dashboard` starts the local Media QA dashboard.
- `npm.cmd run build:dashboard` builds the dashboard static bundle.

## Coding Style & Naming Conventions
Use Python for orchestration and TypeScript/React for Remotion. Keep one node responsibility per file. Prefer explicit schemas and contracts. Use snake_case in Python and PascalCase for React.

## Testing Guidelines
Prioritize deterministic tests for prompt hashing, provider contracts, approvals, reports, file naming, retry policy, timeline math, state transitions, checkpoint resume, renderer payloads, and scene retry flows.

The local end-to-end test invokes Remotion and requires installed Node dependencies. Image retry is per scene and bounded to three total attempts unless the CLI explicitly overrides it. A render failure is retried by a later `resume`, never by an unbounded loop. Keep the latest validated checkpoint and do not delete fingerprint manifests when diagnosing recovery.

Default tests must set or preserve `TTS_PROVIDER=local`; they must never discover a developer `.env` and consume Gemini quota. Test Google request behavior with an injected fake client. Run the live smoke command only as an explicit verification step.

## Commit & Pull Request Guidelines
Use short imperative commits. Do not implement on `main` unless approved. PRs should link `/goals`, describe impact, list validation, note services, include render samples for video changes, and state rollback.

## Goals & Recovery Workflow
Before editing, check `/goals`, branch, and `git status --short --branch`. Keep one goal per slice and commit verified milestones. For unmerged failures, switch to a known-good branch. For merged regressions, prefer `git revert`.

## Context Handoff
At feature end, update `AGENTS.md` for new commands, rules, tests, recovery steps, or limitations, then use fresh context when possible. If context is near full mid-feature, compact first and preserve goal, branch, changes, validation, blockers, and next command.

## Security & Config
Store secrets in `.env` and commit only `.env.example`. Never log keys or tokens. Validate file names, MIME types, sizes, and project paths. Route external operations through reviewed wrappers.

Gemini TTS publishes mono PCM16 WAV at 24 kHz, retries only transient failures with a finite bound, and has no automatic local fallback. Smoke outputs must remain under repository `tmp/`.

The dashboard is read-only in the first slice; do not add pipeline execution, approval writes, or upload actions without a new goal and tests.

Local content, SVG image, and tone-WAV providers are deterministic POC adapters. Gemini TTS is Preview and does not prove production capacity. AI-generated images and YouTube upload remain out of scope.
