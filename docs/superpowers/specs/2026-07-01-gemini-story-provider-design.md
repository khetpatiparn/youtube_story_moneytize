# Gemini Story Provider Design

**Status:** Approved in chat on 2026-07-01

## Goal

Replace deterministic template story content in intentional live runs with one
structured Gemini request that produces a Thai narration and English Flux prompt for
every scene. Preserve the local provider as the default for deterministic, quota-free
tests and keep the existing script approval, checkpoint, image, TTS, render, QA, and
dashboard flow intact.

## Provider and Model Choice

Use the official Google Gen AI Python SDK and `gemini-2.5-flash` by default. The model
supports structured output and is currently available on the Gemini Developer API Free
Tier. Free Tier availability and limits are operational constraints, not capacity
guarantees.

Alternatives rejected for this slice:

- `gemini-2.5-flash-lite` is cheaper and faster but trades away story and prompt quality.
- Separate outline and script calls provide more editorial control but double request
  count and complicate retry/idempotency.
- A local LLM would add model storage and hardware requirements that are unsuitable for
  the default Windows POC environment.

## Architecture

Add a synchronous `GeminiStoryProvider` behind the existing `StoryProvider.generate_story`
contract. It wraps an injected `GeminiStoryClient`, allowing unit tests to supply
structured fake responses without importing credentials or making network requests.

The production adapter wraps `google.genai.Client.models.generate_content` and requests
JSON with a Pydantic schema. One request receives topic, target duration, language,
channel profile, script version, exact target scene count, narrative rules, and image
prompt rules.

Gemini returns only:

```text
story_title
scenes[]:
  title
  narration
  image_prompt
```

The provider, not Gemini, assigns ordered IDs (`scene_001` onward), `slow_push` motion,
center focal points, outline beats, and the joined script. This keeps downstream content
contracts deterministic and prevents the model from controlling file identities or
renderer behavior.

## Story and Scene Contract

Target scene count uses the existing formula:

```python
max(3, min(8, round(duration_seconds / 10)))
```

The response must contain exactly that many scenes. Narration is natural Thai suitable
for spoken storytelling, with total pacing guided by the requested duration. Image
prompts are English, visual-only, contain no dialogue or written text, keep the primary
subject near the center for a 16:9 crop, and repeat stable character/art-direction traits
across scenes for Flux continuity.

The provider normalizes surrounding whitespace but does not silently invent missing
content. It rejects empty titles, narration, or prompts; duplicate scene titles; wrong
scene count; excessively long fields; non-Thai narration; and output that fails the
Pydantic or downstream `ContentPipeline` contract. Thai detection requires at least one
Thai Unicode character in every narration, while allowing names and occasional foreign
terms.

Bounded field limits are:

- story title: 1–200 characters;
- scene title: 1–200 characters;
- narration: 1–4,000 characters per scene;
- image prompt: 1–2,048 characters per scene;
- topic supplied to the prompt: at most 500 characters after normalization.

The final `script` is exactly the scene narrations joined by two newlines and outline
beats exactly match scene titles, satisfying the existing artifact validator.

## Configuration and Pipeline Wiring

Environment variables:

- `LLM_PROVIDER=local|google`, default `local`;
- `GEMINI_API_KEY`, shared with Gemini TTS;
- `GEMINI_LLM_MODEL=gemini-2.5-flash`;
- `GEMINI_LLM_MAX_ATTEMPTS=3`, constrained to 1–5;
- `GEMINI_LLM_TEMPERATURE=0.7`, constrained to 0–2.

`create`, `status`, approval commands, reporting, and resume of an existing checkpoint do
not construct or call the story provider. A fresh `run` constructs the configured story
provider before content generation. Unknown providers and missing Google configuration
fail before content artifacts or checkpoints are mutated.

`PipelineRunner` receives an optional content provider and passes it to
`ContentPipeline`. Direct tests and callers that do not inject a provider retain the
local deterministic default. Successful state records `content_provider` and
`content_model`; local runs record `local` and `deterministic-story-v1`.

No Google-to-local fallback occurs after a live failure.

## Error Handling and Retry

`GeminiStoryProvider` owns retries because content generation occurs before the first
checkpoint. Retry timeout, connection, HTTP 429, HTTP 5xx, and an otherwise successful
response with missing structured output. Use bounded delays of 1, 2, and 4 seconds,
capped by the configured attempt limit.

Authentication, permission, missing model, invalid request, safety rejection, schema
violation, wrong scene count, and semantic content validation are permanent failures.
Public errors are sanitized and never contain API keys, raw provider bodies, generated
story text, prompts, or account/project identifiers.

The provider holds the complete structured response in memory. `ContentPipeline`
validates the normalized contract and publishes outline, script, and scenes together
through `ArtifactStore.publish_bytes_set`. A failed request or validation writes no
content artifacts. A failed atomic publication restores the previous complete artifact
set according to existing ArtifactStore behavior.

## Safe Live Smoke Command

Add:

```powershell
python -m app smoke-google-story `
  --topic "วิญญาณแม่น้ำผู้พิทักษ์หมู่บ้าน" `
  --duration 30 `
  --profile simple_story_th `
  --output tmp/gemini-story-smoke.json
```

The command always selects Google explicitly, validates all configuration before client
construction, permits only a relative `.json` path below repository `tmp/`, runs one
bounded provider operation, validates the final downstream content contract, and
atomically writes the generated story JSON.

Stdout contains only `model`, `scene_count`, `script_characters`, and `output_path`.
It does not print the API key, topic, prompt, narration, image prompts, raw response, or
full story. The command never runs during test discovery.

## Testing Strategy

Default subprocess tests explicitly use `LLM_PROVIDER=local`, `IMAGE_PROVIDER=local`,
and `TTS_PROVIDER=local`. No default test constructs the production Gemini client.

Fake-client provider tests cover:

- one request with model, schema, temperature, topic, duration, profile, version, and
  exact scene count;
- deterministic normalization into the existing outline/script/scenes contract;
- Thai narration and English image-prompt expectations;
- scene count and all field bounds;
- duplicate, blank, malformed, unsafe, and schema-invalid output;
- retryable success, exact exhaustion, permanent failure, and error sanitization;
- no partial artifact publication after provider or validation failure;
- configuration selection and no provider construction for non-run commands;
- smoke output/path restrictions and absence of credentials or story text on stdout.

The existing local CLI-to-MP4 test stays deterministic. Live acceptance runs the story
smoke once, then a short fresh project with `LLM_PROVIDER=google`,
`IMAGE_PROVIDER=cloudflare`, and `TTS_PROVIDER=google` through final approval. Evidence
must show `content_provider=google`, Cloudflare JPEG scene jobs, Google narration, a valid
MP4, passing QA, and dashboard data.

## Security, Free Tier, and Data Use

- Secrets remain only in ignored `.env` or process environment.
- Prompt and response content are not logged by this application.
- Model, retries, temperature, field sizes, scene count, and output paths are bounded.
- Free Tier prompts and outputs may be used by Google to improve products; do not submit
  confidential stories or personal data without reviewing current terms.
- Rate limits and model availability can change. Exhaustion stops the pipeline and never
  opts into paid usage or another provider automatically.
- Safety rejection requires a human topic or prompt change.

## Delivery and Rollback

Develop on `gemini-story-provider` with TDD and verified commits. Completion requires a
live smoke, a fresh end-to-end Gemini-story/Cloudflare-image/Gemini-TTS sample through
final approval, full orchestrator/renderer/dashboard suites, dashboard production build,
compile checks, `git diff --check`, documentation, final review, merge, and pushed main
with matching local/remote commit IDs.

Rollback is a normal revert of the merge commit. Operators can immediately set
`LLM_PROVIDER=local` to stop external story calls without changing image or TTS provider
selection.
