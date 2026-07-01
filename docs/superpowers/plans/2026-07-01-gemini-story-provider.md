# Gemini Story Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate validated Thai story scripts and English Flux prompts with one Gemini 2.5 Flash structured request per script version while preserving deterministic local tests.

**Architecture:** `GeminiStoryProvider` implements the synchronous `StoryProvider` contract through an injected structured-output client and normalizes model output into deterministic downstream scene identities. Environment wiring selects local or Google only for fresh content runs, while a safe smoke command validates one live response without printing story text or credentials.

**Tech Stack:** Python 3.11+, official `google-genai`, Pydantic, `unittest`, existing ArtifactStore/checkpoint pipeline, Gemini 2.5 Flash structured output.

---

### Task 1: Gemini Structured Story Provider

**Files:**
- Create: `apps/orchestrator/src/app/providers/gemini_story.py`
- Create: `apps/orchestrator/tests/test_gemini_story_provider.py`

- [ ] **Step 1: Write RED fake-client contract tests**

Use a fake `GeminiStoryClient` that records `model`, prompt, response schema, and
temperature. Return exactly three scenes for a 1-second request and assert:

```python
story = provider.generate_story("วิญญาณแม่น้ำ", 1, "th", "simple_story_th", 1)
self.assertEqual(story["outline"]["beats"], [scene["title"] for scene in story["scenes"]])
self.assertEqual(story["script"], "\n\n".join(scene["narration"] for scene in story["scenes"]))
self.assertEqual([scene["scene_id"] for scene in story["scenes"]],
                 ["scene_001", "scene_002", "scene_003"])
self.assertTrue(all(scene["motion"] == "slow_push" for scene in story["scenes"]))
```

Assert one client call, the exact scene-count formula, Thai narration, English image
prompt instructions, normalized fields, deterministic output, and no API key in prompt.

- [ ] **Step 2: Add RED validation, retry, and sanitization tests**

Cover blank/missing/malformed output; wrong scene count; duplicate titles; narration
without Thai characters; story/scene title over 200 characters; narration over 4,000;
image prompt over 2,048; topic over 500 after normalization; retryable success; exact
attempt exhaustion; permanent failure without retry; missing structured response; and
exceptions containing key/raw story/prompt whose public message contains none of them.

- [ ] **Step 3: Confirm RED**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_gemini_story_provider.py -v
```

Expected: import failure for `app.providers.gemini_story`.

- [ ] **Step 4: Implement response schema, provider, and adapter**

Create Pydantic models `GeminiSceneResponse(title, narration, image_prompt)` and
`GeminiStoryResponse(story_title, scenes)`. Define:

```python
class GeminiStoryClient(Protocol):
    def generate_story(self, *, model: str, prompt: str,
                       response_schema: type[BaseModel], temperature: float) -> dict[str, Any]:
        pass
```

`GoogleGenAIStoryClient` calls `client.models.generate_content` with
`GenerateContentConfig(response_mime_type="application/json",
response_schema=GeminiStoryResponse, temperature=temperature)` and returns
`response.parsed.model_dump()`. Missing parsed output is retryable. Map timeout, 429, and
5xx to sanitized retryable errors; other SDK failures to sanitized permanent errors.

`GeminiStoryProvider` validates constructor model/attempts/temperature, computes exact
scene count, builds the bounded prompt, retries with injected sleep delays 1/2/4, parses
the Pydantic response, validates semantic limits, and returns exactly
`outline`, `script`, and `scenes`. It assigns IDs, motion, and focal points itself.

- [ ] **Step 5: Verify and commit**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_gemini_story_provider.py -v
python -m unittest discover apps/orchestrator/tests
python -m compileall apps/orchestrator/src/app/providers/gemini_story.py
git diff --check
git add apps/orchestrator/src/app/providers/gemini_story.py apps/orchestrator/tests/test_gemini_story_provider.py
git commit -m "feat: add Gemini structured story provider"
```

### Task 2: Content Metadata and Environment Wiring

**Files:**
- Modify: `apps/orchestrator/src/app/services/content_pipeline.py`
- Modify: `apps/orchestrator/src/app/services/pipeline_runner.py`
- Modify: `apps/orchestrator/src/app/services/config.py`
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Modify: `apps/orchestrator/tests/test_local_content_pipeline.py`
- Modify: `apps/orchestrator/tests/test_pipeline_runner.py`
- Modify: `apps/orchestrator/tests/test_provider_config.py`
- Modify: `apps/orchestrator/tests/test_cli.py`
- Modify: `apps/orchestrator/tests/test_end_to_end.py`
- Modify: `.env.example`

- [ ] **Step 1: Write RED metadata/config/gating tests**

Test `build_story_provider(store, environ)` for default/local, Google with patched client,
missing key, unknown provider, blank/invalid model, attempts outside 1–5, and temperature
outside 0–2. Assert errors omit supplied credentials.

Test `ContentPipeline` records provider/model for local and injected providers. Test a
fresh CLI `run` with `LLM_PROVIDER=unknown` fails before outline/script/scenes or a
checkpoint is written, while `create`, `status`, approvals, report, and resume of an
existing checkpoint do not construct a story provider. All subprocess tests that run
content set `LLM_PROVIDER=local` explicitly.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_provider_config.py apps/orchestrator/tests/test_local_content_pipeline.py apps/orchestrator/tests/test_cli.py -v
```

Expected: missing story builder and content metadata.

- [ ] **Step 3: Expose reusable content validation and metadata**

Move the static validation body to public
`validate_story_content(content: Any) -> None`; `ContentPipeline.generate` calls it.
After atomic publication, include:

```python
"content_provider": getattr(self.provider, "provider", "unknown"),
"content_model": getattr(self.provider, "model", "unknown"),
```

Keep the generated content dictionary restricted to outline/script/scenes.

- [ ] **Step 4: Implement configuration and fresh-run injection**

Add `build_story_provider(store, environ)` using `LLM_PROVIDER` default local. For Google,
validate `GEMINI_API_KEY`, `GEMINI_LLM_MODEL`, integer attempts 1–5, and finite float
temperature 0–2 before client construction.

Add optional `content_provider` to `PipelineRunner`; fresh content uses
`ContentPipeline(store, self.content_provider)`. In CLI, `_run_project` calls
`_build_pipeline_runner(args, configure_content=True)`. Build the story provider only
for that fresh-run path; existing checkpoint `run` and `resume` reuse state without a
story request. Validate configuration before invoking `PipelineRunner.run` so invalid
config creates no content artifacts/checkpoint.

Update `.env.example` with `LLM_PROVIDER=local`, model, attempts, temperature, and a
comment that automated tests require local providers.

- [ ] **Step 5: Verify and commit**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_provider_config.py apps/orchestrator/tests/test_local_content_pipeline.py apps/orchestrator/tests/test_pipeline_runner.py apps/orchestrator/tests/test_cli.py apps/orchestrator/tests/test_end_to_end.py -v
python -m unittest discover apps/orchestrator/tests
git diff --check
git add .env.example apps/orchestrator/src/app/services/content_pipeline.py apps/orchestrator/src/app/services/pipeline_runner.py apps/orchestrator/src/app/services/config.py apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_local_content_pipeline.py apps/orchestrator/tests/test_pipeline_runner.py apps/orchestrator/tests/test_provider_config.py apps/orchestrator/tests/test_cli.py apps/orchestrator/tests/test_end_to_end.py
git commit -m "feat: select story provider for fresh runs"
```

### Task 3: Safe Gemini Story Smoke Command

**Files:**
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Create: `apps/orchestrator/tests/test_gemini_story_smoke.py`

- [ ] **Step 1: Write RED smoke tests**

With an injected fake client, assert `smoke-google-story` writes validated JSON below
`tmp/` and stdout contains exactly:

```python
{"model", "scene_count", "script_characters", "output_path"}
```

Cover empty/overlong topic, invalid duration/profile/output, missing key before client,
unsafe/absolute/non-JSON path, retry exhaustion, permanent failure, parser routing, and
absence of API key/topic/narration/image prompt/raw response on stdout/stderr.

- [ ] **Step 2: Confirm RED and implement**

Add parser arguments `--topic`, `--duration` (positive integer), `--profile`, and default
`--output tmp/gemini-story-smoke.json`. `_smoke_google_story` validates path and config,
constructs Google explicitly, calls the provider once with its internal bounded retry,
calls `validate_story_content`, atomically writes UTF-8 JSON, and prints only approved
metadata fields. Expected provider/config errors become sanitized `SystemExit`.

- [ ] **Step 3: Verify and commit**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_gemini_story_smoke.py -v
python -m unittest discover apps/orchestrator/tests
git diff --check
git add apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_gemini_story_smoke.py
git commit -m "feat: add safe Gemini story smoke command"
```

### Task 4: Live Acceptance, Documentation, and Delivery

**Files:**
- Create: `goals/gemini-story-provider.md`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Verify credentials without exposing values**

Confirm ignored `.env` has a non-empty `GEMINI_API_KEY`, `LLM_PROVIDER=google`, model,
attempts, and temperature using boolean-only output. Never print the file or values.

- [ ] **Step 2: Run one live story smoke**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m app smoke-google-story --topic "วิญญาณแม่น้ำผู้พิทักษ์หมู่บ้าน" --duration 30 --profile simple_story_th --output tmp/gemini-story-smoke.json
```

Confirm valid JSON, natural Thai narration, English image prompts, exact scene count, and
sanitized stdout.

- [ ] **Step 3: Run fresh end-to-end external-provider acceptance**

Create a new short project, run with Google story provider to script approval, approve,
then resume with Cloudflare images and Gemini TTS to final approval. Confirm state records
`content_provider=google`, the configured content model, Cloudflare JPEG jobs, Google
24-kHz narration, playable MP4, QA score 1.0, and dashboard paths.

- [ ] **Step 4: Document and record evidence**

Document LLM environment variables, one-call architecture, smoke command, Free Tier/data
use, retry/no-fallback behavior, local tests, field/scene bounds, and recovery. Record
only sanitized live metadata in `goals/gemini-story-provider.md`.

- [ ] **Step 5: Run fresh completion verification**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest discover apps/orchestrator/tests
python -m compileall apps/orchestrator/src
npm.cmd run test:renderer
npm.cmd run test:dashboard
npm.cmd run build:dashboard
git diff --check
git status --short --branch
```

- [ ] **Step 6: Commit docs, review, merge, reverify, and push**

Commit documentation, review the complete diff for credential leakage, accidental quota,
schema bypass, retries, and checkpoint regressions, then merge into `main`. Re-run the
full verification on merged main, push, verify local/remote SHA equality, update the goal
status, and clean only worktrees/branches created for this feature.
