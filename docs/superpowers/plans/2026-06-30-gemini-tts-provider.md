# Gemini Thai TTS Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add natural Thai Gemini narration to real pipeline runs without consuming API quota in default tests or weakening checkpoint recovery.

**Architecture:** `GeminiTTSProvider` implements the existing async provider contract using an injected official Google client. Environment-driven construction chooses Google or local TTS, while shared WAV validation accepts both supported PCM rates and the live smoke command is the only default path that intentionally calls Gemini.

**Tech Stack:** Python 3.11+, `google-genai`, `python-dotenv`, `unittest`, Gemini TTS Preview, PCM/WAV, existing SQLite/Remotion pipeline.

---

## Task 1: Multi-Rate WAV Contract

**Files:**
- Modify: `apps/orchestrator/src/app/services/timeline.py`
- Modify: `apps/orchestrator/src/app/providers/local.py`
- Modify: `apps/orchestrator/tests/test_local_audio_timeline.py`

- [ ] **Step 1: Add failing 24 kHz and unsupported-rate tests**

Add tests that create valid mono PCM16 WAVs at 22,050 and 24,000 Hz and assert
`wav_metadata(path)` returns frames, sample rate, and duration. Add a 44,100 Hz case
that raises `ValueError`, plus truncated-data coverage at both allowed rates.

- [ ] **Step 2: Run the focused test and confirm RED**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_local_audio_timeline.py -v
```

Expected: failure because `wav_metadata` and 24 kHz support do not exist.

- [ ] **Step 3: Implement one shared WAV metadata validator**

Define immutable `WavMetadata(sample_rate, frame_count, duration_seconds)` and
`wav_metadata(path, allowed_sample_rates=(22050, 24000))`. Require uncompressed mono
PCM16, positive frames, exact readable byte length, and a finite positive duration.
Make `wav_duration_seconds` return `wav_metadata(path).duration_seconds`. Keep local
TTS at 22,050 Hz.

- [ ] **Step 4: Run focused and full orchestrator tests**

Expected: both sample rates pass, unsupported/truncated files fail, existing timeline
math remains green.

- [ ] **Step 5: Commit**

```powershell
git add apps/orchestrator/src/app/services/timeline.py apps/orchestrator/src/app/providers/local.py apps/orchestrator/tests/test_local_audio_timeline.py
git commit -m "feat: support Gemini WAV sample rate"
```

## Task 2: Gemini Provider Core

**Files:**
- Create: `apps/orchestrator/src/app/providers/gemini_tts.py`
- Create: `apps/orchestrator/tests/test_gemini_tts_provider.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write fake-client provider tests**

Use a fake client that records model, transcript, voice, and audio modality. Cover:

```python
result = await provider.synthesize(
    "ย่อหน้าแรก\n\nย่อหน้าที่สอง",
    "Charon",
    "audio/narration.wav",
    {},
)
self.assertEqual(result.provider, "google")
self.assertEqual(result.model, "gemini-3.1-flash-tts-preview")
self.assertEqual(wav_metadata(store.path(result.output_path)).sample_rate, 24000)
```

Assert paragraph ordering, one client call per chunk, byte-exact PCM concatenation,
Thai performance instructions, output path, and measured duration.

- [ ] **Step 2: Confirm RED**

Run `python -m unittest apps/orchestrator/tests/test_gemini_tts_provider.py -v`.
Expected: import failure for `GeminiTTSProvider`.

- [ ] **Step 3: Add official dependencies**

Add bounded compatible dependencies:

```toml
"google-genai>=1,<2",
"python-dotenv>=1,<2",
```

Install the project dependencies before live verification.

- [ ] **Step 4: Implement provider and client protocol**

Create `GeminiSpeechClient` protocol with one async `generate_pcm` method. The real
adapter wraps `google.genai.Client` and requests audio-only single-speaker output.
`GeminiTTSProvider` accepts store, API key, model, voice, max attempts, client,
sleep function, and chunk limit. It splits non-empty paragraphs and long text at
sentence/whitespace boundaries without losing characters.

Validate each response as non-empty even-length PCM bytes. Retry rate-limit/server/no-
audio errors at most `max_attempts` per chunk with bounded exponential delays. Convert
auth/permission/model/request failures and retry exhaustion to sanitized provider
errors. Stage all PCM in memory and publish one 24 kHz WAV only after all chunks pass.

- [ ] **Step 5: Add failure and atomicity tests**

Cover transient success after retry, exact attempt bound, permanent errors, empty and
odd-length audio, overlong splitting, and preservation of an existing WAV when a later
chunk fails. Assert exceptions contain no API key or raw response.

- [ ] **Step 6: Run tests and commit**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_gemini_tts_provider.py -v
python -m unittest discover apps/orchestrator/tests
git diff --check
git add pyproject.toml apps/orchestrator/src/app/providers/gemini_tts.py apps/orchestrator/tests/test_gemini_tts_provider.py
git commit -m "feat: add Gemini Thai TTS provider"
```

## Task 3: Environment Selection and Pipeline Wiring

**Files:**
- Create: `apps/orchestrator/src/app/services/config.py`
- Create: `apps/orchestrator/tests/test_provider_config.py`
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Modify: `apps/orchestrator/tests/test_cli.py`
- Modify: `apps/orchestrator/tests/test_end_to_end.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing configuration tests**

Test that `.env` loads without overriding existing environment values, `local`
constructs `LocalTTSProvider`, `google` requires a non-empty key and constructs
`GeminiTTSProvider`, and unknown providers fail before any artifact mutation. Assert
errors never contain credential values.

- [ ] **Step 2: Confirm RED**

Run `python -m unittest apps/orchestrator/tests/test_provider_config.py -v`.
Expected: missing config module.

- [ ] **Step 3: Implement config and runner construction**

`load_environment(repository_root)` calls `load_dotenv(repository_root / ".env",
override=False)`. `build_tts_provider(store, environ)` validates provider/model/voice/
attempt settings. `_build_pipeline_runner` injects the selected provider. Project
creation and script-pause commands must not call the provider.

Default automated tests set `TTS_PROVIDER=local` explicitly so a developer's `.env`
cannot trigger API calls. Update `.env.example` with empty key, model, voice, attempt
limit, and a comment that local is required for deterministic tests.

- [ ] **Step 4: Verify pipeline selection and commit**

Run configuration, CLI, end-to-end, and full suites. Assert fake Google selection is
used only after script approval and checkpoint retry semantics remain unchanged.

```powershell
git add .env.example apps/orchestrator/src/app/services/config.py apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_provider_config.py apps/orchestrator/tests/test_cli.py apps/orchestrator/tests/test_end_to_end.py
git commit -m "feat: select TTS provider from environment"
```

## Task 4: Safe Live Smoke Command

**Files:**
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Create: `apps/orchestrator/tests/test_google_tts_smoke.py`

- [ ] **Step 1: Write failing smoke-command tests**

Inject a fake Gemini client and assert the command writes the requested WAV and prints
only JSON fields `model`, `voice`, `sample_rate`, `duration_seconds`, and `output_path`.
Assert stdout/stderr contain neither API key nor transcript, missing credentials fail
before client construction, and output is constrained to the repository `tmp/` path.

- [ ] **Step 2: Confirm RED and implement**

Add:

```powershell
python -m app smoke-google-tts --text "สวัสดี นี่คือเสียงทดสอบ" --output tmp/gemini-tts-smoke.wav
```

The command always selects Google explicitly, validates the generated WAV with
`wav_metadata`, and emits sanitized metadata JSON. It is never invoked by discovery.

- [ ] **Step 3: Run fake smoke tests and commit**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_google_tts_smoke.py -v
git add apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_google_tts_smoke.py
git commit -m "feat: add safe Gemini TTS smoke command"
```

## Task 5: Live Verification, Documentation, and Delivery

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `goals/gemini-tts-provider.md`

- [ ] **Step 1: Run live smoke once**

Run the smoke command with the ignored `.env`. Confirm exit zero, 24 kHz mono PCM16,
positive duration, non-empty output, and no secret in terminal output. Do not capture
or print environment values.

- [ ] **Step 2: Run a Google-backed pipeline sample**

Create a new short project, pause for script approval, resume with Google TTS, and
confirm final approval pause, `voice_provider=google`, a valid 24 kHz WAV, real MP4,
quality report, and dashboard live data. Use no automatic local fallback.

- [ ] **Step 3: Document setup and constraints**

Document environment variables, smoke command, Free Tier limits, Preview instability,
retry behavior, Google Free Tier data use, chunking, and local deterministic tests.
Never include actual credentials or generated secret-bearing logs.

- [ ] **Step 4: Run completion verification**

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

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md AGENTS.md goals/gemini-tts-provider.md
git commit -m "docs: document Gemini TTS workflow"
```
