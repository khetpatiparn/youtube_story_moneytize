# Repository Guidelines

## Project Structure & Module Organization
This repository contains `youtube_story_automation_poc_plan.md` plus an initial Python orchestrator skeleton. The planned system uses LangGraph and Remotion.

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
- `python -m app run --project-id project_001` runs the hello-world graph.
- `python -m app status --project-id project_001` inspects progress.
- `npx remotion render src/index.ts YouTubeStory ...` to render video output.

## Coding Style & Naming Conventions
Use Python for orchestration and TypeScript/React for Remotion. Keep one workflow node responsibility per file. Prefer explicit schemas for LLM outputs and provider contracts. Use snake_case in Python and PascalCase for React components.

## Testing Guidelines
Prioritize deterministic tests for prompt hashing, cache behavior, file naming, retry policy, timeline calculations, and state transitions. Add Pydantic schema tests and integrations for topic-to-script, script-to-scenes, voice-to-timeline, resume, and scene retry flows.

## Commit & Pull Request Guidelines
Use short imperative commit messages such as `Add orchestrator skeleton`. Do not implement on `main` unless explicitly approved; create one focused branch per slice. Pull requests should link `/goals`, describe workflow impact, list validation, note services, include render samples for UI/video changes, and state rollback.

## Goals & Recovery Workflow
Before editing, check `/goals`, branch, and `git status --short --branch`. Keep one goal per slice and commit after verified milestones. For unmerged failures, switch to a known-good branch. For merged regressions, prefer `git revert`.

## Context Handoff
At feature end, update `AGENTS.md` for new commands, layout rules, tests, recovery steps, or limitations, then start the next feature with fresh context when possible. If context is near full mid-feature, compact first and preserve goal, branch, changed files, validation, blockers, and next command.

## Security & Config
Store secrets in `.env` and commit only `.env.example`. Never log keys or OAuth tokens. Validate file names, MIME types, sizes, and project paths. Route external operations through reviewed wrappers.
