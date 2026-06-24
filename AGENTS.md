# Repository Guidelines

## Project Structure & Module Organization
This repository contains `youtube_story_automation_poc_plan.md` plus a Python orchestrator with checkpoints and provider contracts. The planned system uses LangGraph and Remotion.

When code is added, keep the planned layout:
- `apps/orchestrator/src/` for graph, nodes, schemas, providers, services, repositories, and CLI.
- `apps/orchestrator/tests/` for Python tests.
- `apps/renderer/src/` for Remotion compositions, components, motions, and `index.ts`.
- `configs/` for prompts, channel profiles, and render profiles.
- `projects/{project_id}/` for generated assets, reports, logs, and renders.
- `data/` for checkpoints and caches.

## Build, Test, and Development Commands
Use `$env:PYTHONPATH='apps/orchestrator/src'` before commands unless installed editable.
- `python -m unittest discover apps/orchestrator/tests` runs the current test suite.
- `python -m app create --topic "..." --duration 180 --profile simple_story_th` creates a project.
- `python -m app run --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite` runs and checkpoints.
- `python -m app resume --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite` restores checkpoint state.
- `python -m app status --project-id project_001` inspects progress.
- `npx remotion render src/index.ts YouTubeStory ...` to render video output.

## Coding Style & Naming Conventions
Use Python for orchestration and TypeScript/React for Remotion. Keep one workflow node responsibility per file. Prefer explicit schemas for LLM outputs and provider contracts. Use snake_case in Python and PascalCase for React components.

## Testing Guidelines
Prioritize deterministic tests for prompt hashing, provider contracts, cache behavior, file naming, retry policy, timeline math, state transitions, checkpoint resume, and scene retry flows.

## Commit & Pull Request Guidelines
Use short imperative commits. Do not implement on `main` unless approved; create one focused branch per slice. PRs should link `/goals`, describe impact, list validation, note services, include render samples for UI/video changes, and state rollback.

## Goals & Recovery Workflow
Before editing, check `/goals`, branch, and `git status --short --branch`. Keep one goal per slice and commit after verified milestones. For unmerged failures, switch to a known-good branch. For merged regressions, prefer `git revert`.

## Context Handoff
At feature end, update `AGENTS.md` for new commands, rules, tests, recovery steps, or limitations, then start the next feature with fresh context when possible. If context is near full mid-feature, compact first and preserve goal, branch, changes, validation, blockers, and next command.

## Security & Config
Store secrets in `.env` and commit only `.env.example`. Never log keys or OAuth tokens. Validate file names, MIME types, sizes, and project paths. Route external operations through reviewed wrappers.
