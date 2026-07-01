# Gemini Story Provider

Status: complete

## Scope

Implement a Google Gemini structured story provider that can replace deterministic local story content for intentional live runs while preserving deterministic local tests and existing approval, image, TTS, render, QA, and dashboard flows.

## Delivered

- Added `GeminiStoryProvider` with structured-response normalization, bounded retries, semantic validation, and sanitized public errors.
- Added environment-based story-provider selection with `LLM_PROVIDER=local|google`.
- Recorded `content_provider` and `content_model` in generated project state.
- Added safe `smoke-google-story` CLI command with bounded path/output rules and sanitized stdout.
- Updated `.env.example`, `README.md`, and `AGENTS.md` for Gemini story configuration and test rules.

## Verification

- Unit and integration verification:
  - `python -m unittest apps/orchestrator/tests/test_gemini_story_provider.py -v`
  - `python -m unittest apps/orchestrator/tests/test_provider_config.py apps/orchestrator/tests/test_local_content_pipeline.py apps/orchestrator/tests/test_pipeline_runner.py apps/orchestrator/tests/test_cli.py -v`
  - `python -m unittest apps/orchestrator/tests/test_gemini_story_smoke.py -v`
  - `python -m unittest discover apps/orchestrator/tests`

- Result:
  - `166 tests` passed, `0` failed, `1` skipped.

## Live Evidence

- Boolean-only `.env` check confirmed presence of `GEMINI_API_KEY`, `LLM_PROVIDER`, `IMAGE_PROVIDER`, and `TTS_PROVIDER`.
- Live story smoke completed successfully with sanitized stdout:
  - model: `gemini-2.5-flash`
  - scene_count: `3`
  - script_characters: `526`
  - output_path: `tmp/gemini-story-smoke.json`

- Fresh external-provider acceptance completed successfully for project `gemini_story_live_20260701083913`:
  - first status: `awaiting_script_approval`
  - content provider/model: `google` / `gemini-2.5-flash`
  - scene count: `3`
  - post-approval resume status: `awaiting_final_approval`
  - generated images: `3` JPEG files
  - voice provider/sample rate: `google` / `24000`
  - final status: `completed`
  - quality score: `1.0`
  - required report/render artifacts present: yes

## Notes

- The sandboxed Python interpreter did not automatically expose user-site packages. Live verification therefore used an unsandboxed command with explicit `PYTHONPATH` pointing at the repository source plus the installed user-site package path.
