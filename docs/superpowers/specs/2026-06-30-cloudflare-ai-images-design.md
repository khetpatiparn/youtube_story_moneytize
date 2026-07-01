# Cloudflare AI Scene Images Design

**Status:** Approved in chat on 2026-06-30

## Goal

Replace deterministic SVG review assets in intentional live runs with one real
AI-generated image per story scene, while retaining local SVG generation for
credential-free tests and preserving the existing approval, retry, checkpoint,
render, QA, and dashboard workflow.

## Provider Choice

Use the Cloudflare Workers AI REST API directly from the Python orchestrator with
`@cf/black-forest-labs/flux-1-schnell`.

This route was selected because it avoids deploying a proxy Worker, works from the
existing local CLI, and fits the zero-cost requirement. Cloudflare currently includes
10,000 neurons per day at no charge. Flux Schnell is priced at 4.8 neurons per
512-by-512 tile plus 9.6 neurons per diffusion step. These values are documentation,
not a capacity guarantee; live calls must fail closed when the allocation is exhausted.

Alternatives rejected for this slice:

- A Cloudflare Worker proxy adds deployment and another failure surface without
  improving the local POC outcome.
- Gemini image generation would reduce the number of vendors but currently has less
  predictable free access for this repository's zero-cost constraint.
- Local diffusion would require a suitable GPU and model storage and would not be a
  reliable default for this Windows development environment.

## Architecture

Add `CloudflareImageProvider` behind the synchronous scene-oriented interface already
used by `ImagePipeline`. The provider receives an injected `CloudflareImageClient` for
unit tests. The production client sends an authenticated JSON POST to:

`/client/v4/accounts/{account_id}/ai/run/{model}`

The request contains `prompt`, a stable positive `seed`, and `steps` (default 4,
allowed 1 through 8). The response must be a successful Cloudflare envelope containing
a non-empty Base64 image. No account identifier, token, prompt, or raw response is
included in normal logs or provider errors.

Environment construction selects the image provider independently from TTS:

- `IMAGE_PROVIDER=local` builds `LocalImageProvider` and requires no credentials.
- `IMAGE_PROVIDER=cloudflare` requires `CLOUDFLARE_ACCOUNT_ID` and
  `CLOUDFLARE_API_TOKEN` and builds `CloudflareImageProvider`.
- `CLOUDFLARE_IMAGE_MODEL` defaults to
  `@cf/black-forest-labs/flux-1-schnell`.
- `CLOUDFLARE_IMAGE_STEPS` defaults to 4 and is constrained to 1 through 8.

Provider construction occurs only after script approval. Creating a project, running
to the script gate, inspecting status, and recording approval do not require or call
Cloudflare.

## Prompt and Continuity Contract

Each scene prompt is deterministic and bounded to Cloudflare's 2,048-character limit.
It combines:

1. A shared visual bible: cinematic illustrated Thai folktale, cohesive palette,
   consistent character design, no text, no watermark, and composition safe for a
   16:9 center crop.
2. Stable project context available in every scene: channel profile and story topic
   already embedded in the source scene prompt.
3. Scene-specific title, prompt, and narration.

The seed is derived from a stable hash of the model, scene ID, and composed prompt.
Retries for the same scene reuse the same prompt and seed. This improves repeatability
and visual continuity but does not guarantee character identity because Flux Schnell's
Cloudflare endpoint has no reference-image contract in this slice.

## Artifact and Validation Contract

The pipeline currently assumes every output is a 1280-by-720 SVG. Generalize it to
support provider-declared output extensions and two validated formats:

- Local: `images/{scene_id}.svg`, MIME `image/svg+xml`, exactly 1280 by 720 with the
  existing namespace and viewBox checks.
- Cloudflare: `images/{scene_id}.jpg`, MIME `image/jpeg`, decoded by Pillow as JPEG,
  non-empty, structurally valid, and with positive dimensions between 512 and 4096
  pixels per side.

The renderer already uses `object-fit: cover`; square or non-16:9 Cloudflare output is
center-cropped into the 1280-by-720 composition. Prompt wording keeps important subjects
near the center.

Cloudflare bytes are staged in memory, decoded and validated before publication, then
written through `ArtifactStore.publish_bytes_set`. An existing valid image is not
replaced when a request, decode, or validation step fails. Job metadata and scene JSON
remain atomically published by `ImagePipeline` after each attempt.

Completed checkpoint jobs are reused only when path containment, extension, MIME,
format, dimensions, and non-empty file validation all pass. Corrupt completed jobs
consume the next bounded attempt; they never silently pass into Remotion.

## Errors, Retry, and Recovery

The Cloudflare client classifies timeout, connection failure, HTTP 429, and HTTP 5xx as
`RetryableProviderError`. Authentication, permission, invalid account/model/input,
other HTTP 4xx, malformed JSON, invalid Base64, and invalid JPEG become sanitized
`PermanentProviderError` unless the response explicitly represents a transient service
failure.

`ImagePipeline` remains the sole retry owner for project runs. It persists attempt state
after every failure and enforces `--max-image-attempts` across process restarts. There is
no Cloudflare-to-local fallback. Retrying or resuming never regenerates a completed,
validated scene.

Unexpected implementation errors are persisted as unexpected failures and re-raised.
Raw exception bodies are chained for debugging but never included in user-facing error
messages or serialized job errors.

## Safe Live Smoke Command

Add:

```powershell
python -m app smoke-cloudflare-image `
  --prompt "cinematic Thai folktale river spirit" `
  --output tmp/cloudflare-image-smoke.jpg
```

The command always selects Cloudflare explicitly and accepts output only under the
repository `tmp/` directory with a `.jpg` suffix. It validates the image and prints only
JSON fields: `model`, `seed`, `steps`, `width`, `height`, `mime_type`, and `output_path`.
It prints neither prompt nor credentials. Missing credentials fail before client
construction. Smoke retry is explicitly bounded by the configured maximum and never
runs during test discovery.

## Testing Strategy

Default tests set `IMAGE_PROVIDER=local` where the CLI can load a developer `.env`.
No normal test constructs the production Cloudflare client or makes a network request.

Fake-client tests cover:

- endpoint request fields, deterministic prompt and seed, model and step selection;
- successful Base64 JPEG decode and atomic publication;
- timeout, 429, 5xx, 4xx, malformed envelopes, invalid Base64, non-JPEG bytes, unsafe
  paths, and credential sanitization;
- exact retry bounds, retry persistence, checkpoint reuse, corrupt-output repair, and
  preservation of a prior valid file when a later operation fails;
- local SVG and Cloudflare JPEG validation paths;
- environment selection and the rule that pre-approval commands do not require keys;
- smoke output fields and prohibition on credential/prompt disclosure;
- renderer payloads and dashboard records referencing `.jpg` scene images.

The existing local CLI-to-MP4 test remains deterministic. Live acceptance is a separate
intentional sequence: one smoke image, then a short approved project using Cloudflare
images and Gemini TTS through final approval. Evidence must show every generated scene
job has provider `cloudflare`, MIME `image/jpeg`, validated `.jpg` files, a playable MP4,
passing QA, and exported dashboard data.

## Security and Operational Limits

- Secrets remain only in ignored `.env` or process environment and are never returned,
  logged, committed, or embedded in artifacts.
- Account ID is treated as configuration metadata but is still omitted from routine
  output to minimize disclosure.
- Output paths are project-relative and containment-checked.
- Prompt length, model, steps, response size, decoded image size, and retry count are
  bounded before publication.
- Free allocation and model availability can change. The CLI reports sanitized failure
  and stops; it does not incur paid usage automatically or switch providers.
- Content safety rejection is permanent for that prompt and requires a human prompt or
  script change.

## Delivery and Rollback

Implementation is developed on `cloudflare-ai-images` in verified commits. Completion
requires orchestrator, renderer, dashboard, local end-to-end tests, compile checks,
dashboard production build, and `git diff --check`, plus the explicit live acceptance
evidence above. Documentation updates include setup, token scope, Free Tier caveats,
commands, retry behavior, and the continuity limitation.

Rollback is a normal revert of the final merge commit. Operators can immediately set
`IMAGE_PROVIDER=local` to avoid external calls without changing persisted projects.
