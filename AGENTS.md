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
- `python -m app create --topic "..." --duration 180 --profile simple_story_th` creates a project.
- `python -m app run --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite` runs and checkpoints.
- `python -m app resume --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite` restores checkpoint state.
- `python -m app status --project-id project_001` inspects progress.
- `python -m app approve-script --project-id project_001 --approved --reviewer human` records approval.
- `python -m app approve-final --project-id project_001 --changes-requested --reviewer human` records final review.
- `python -m app report --project-id project_001 --video-path render/story.mp4 --quality-score 0.91` writes reports.
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

## Commit & Pull Request Guidelines
Use short imperative commits. Do not implement on `main` unless approved. PRs should link `/goals`, describe impact, list validation, note services, include render samples for video changes, and state rollback.

## Goals & Recovery Workflow
Before editing, check `/goals`, branch, and `git status --short --branch`. Keep one goal per slice and commit verified milestones. For unmerged failures, switch to a known-good branch. For merged regressions, prefer `git revert`.

## Context Handoff
At feature end, update `AGENTS.md` for new commands, rules, tests, recovery steps, or limitations, then use fresh context when possible. If context is near full mid-feature, compact first and preserve goal, branch, changes, validation, blockers, and next command.

## Security & Config
Store secrets in `.env` and commit only `.env.example`. Never log keys or tokens. Validate file names, MIME types, sizes, and project paths. Route external operations through reviewed wrappers.

The dashboard is read-only in the first slice; do not add pipeline execution, approval writes, or upload actions without a new goal and tests.
