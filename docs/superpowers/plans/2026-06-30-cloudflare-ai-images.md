# Cloudflare AI Scene Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate one validated Cloudflare Flux JPEG per approved story scene and render those images with Gemini narration while keeping all default tests local and quota-free.

**Architecture:** A synchronous `CloudflareImageProvider` wraps an injected REST client and implements the existing scene-oriented image interface. Shared image validation supports deterministic SVG and Cloudflare JPEG artifacts, while environment construction injects the selected provider only after script approval; `ImagePipeline` remains the single retry and checkpoint owner.

**Tech Stack:** Python 3.11+, `urllib.request`, Pillow, Cloudflare Workers AI REST API, `unittest`, existing SQLite checkpoints, ArtifactStore, Remotion, and Vite dashboard.

---

### Task 1: Provider-Neutral Image Artifact Contract

**Files:**
- Create: `apps/orchestrator/src/app/services/image_validation.py`
- Modify: `apps/orchestrator/src/app/services/image_pipeline.py`
- Modify: `apps/orchestrator/src/app/providers/local.py`
- Modify: `apps/orchestrator/tests/test_image_pipeline.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add Pillow and write failing SVG/JPEG validation tests**

Add `"Pillow>=10,<13"` to project dependencies. In `test_image_pipeline.py`, create a
Pillow JPEG fixture in memory and add tests equivalent to:

```python
def test_image_pipeline_accepts_provider_declared_jpeg_output(self):
    provider = FakeJpegProvider(store, jpeg_bytes(width=1024, height=1024))
    result = ImagePipeline(store, provider).generate([scene("scene_001")])
    job = result["image_jobs"][0]
    self.assertEqual(job["output_path"], "images/scene_001.jpg")
    self.assertEqual(job["mime_type"], "image/jpeg")

def test_image_pipeline_rejects_jpeg_with_wrong_format_or_dimensions(self):
    for content in (b"not-jpeg", jpeg_bytes(width=64, height=64)):
        with self.subTest(size=len(content)):
            provider = FakeJpegProvider(store, content)
            with self.assertRaises(ImageGenerationExhausted):
                ImagePipeline(store, provider, max_attempts=1).generate([scene("scene_001")])
```

Retain explicit tests proving local SVG validation still requires the namespace,
1280-by-720 size, and viewBox.

- [ ] **Step 2: Run focused tests and confirm RED**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps.orchestrator/tests/test_image_pipeline.py -v
```

Expected: JPEG cases fail because `ImagePipeline` always requests `.svg` and only
accepts `image/svg+xml`.

- [ ] **Step 3: Implement shared byte and file validation**

Create `image_validation.py` with immutable
`ImageMetadata(mime_type: str, width: int, height: int, format: str)`. Expose
`validate_image_bytes(content: bytes, mime_type: str) -> ImageMetadata` and
`validate_image_file(path: Path, mime_type: str) -> ImageMetadata`; the file function
reads bytes with an explicit 16 MB limit and delegates to the byte function.

For SVG, parse XML and require the existing namespace root, width `1280`, height `720`,
and viewBox `0 0 1280 720`. For JPEG, open from `BytesIO` with Pillow, call `verify()`,
reopen to load pixels, require format `JPEG`, positive dimensions in `[512, 4096]`, and
reject trailing decode failures. Error messages identify only the invalid property.

- [ ] **Step 4: Make output extension provider-declared**

Set `LocalImageProvider.output_extension = "svg"`. In `ImagePipeline.generate`, replace
the hard-coded path with:

```python
extension = getattr(self.provider, "output_extension", "svg")
if extension not in {"svg", "jpg"}:
    raise PermanentProviderError("unsupported image output extension")
image = self.provider.generate(scene, f"images/{scene_id}.{extension}")
```

Replace `_completed_job_corruption` format-specific parsing with contained-path,
extension/MIME consistency, and `validate_image_file`. Accept only `.svg` with
`image/svg+xml` or `.jpg` with `image/jpeg`.

- [ ] **Step 5: Run focused and full orchestrator tests**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_image_pipeline.py -v
python -m unittest discover apps/orchestrator/tests
git diff --check
```

Expected: all prior SVG behavior remains green and the new JPEG paths pass.

- [ ] **Step 6: Commit the artifact contract**

```powershell
git add pyproject.toml apps/orchestrator/src/app/services/image_validation.py apps/orchestrator/src/app/services/image_pipeline.py apps/orchestrator/src/app/providers/local.py apps/orchestrator/tests/test_image_pipeline.py
git commit -m "feat: validate SVG and JPEG scene images"
```

### Task 2: Cloudflare Flux Provider Core

**Files:**
- Create: `apps/orchestrator/src/app/providers/cloudflare_image.py`
- Create: `apps/orchestrator/tests/test_cloudflare_image_provider.py`

- [ ] **Step 1: Write fake-client provider tests**

Define a fake client that records model and payload and returns a Cloudflare-style
result. Cover successful generation with a real in-memory JPEG fixture:

```python
result = provider.generate(scene, "images/scene_001.jpg")
self.assertEqual(result["provider"], "cloudflare")
self.assertEqual(result["mime_type"], "image/jpeg")
self.assertEqual(client.calls[0]["payload"]["steps"], 4)
self.assertIn("no text", client.calls[0]["payload"]["prompt"])
self.assertEqual(client.calls[0]["payload"]["seed"], expected_seed)
```

Also assert the composed prompt is deterministic, at most 2,048 characters, contains
the common visual bible and scene content, and never includes credentials.

- [ ] **Step 2: Add failing error, atomicity, and sanitization tests**

Cover malformed envelope, missing image, invalid Base64, valid Base64 containing
non-JPEG bytes, unsafe output path, request payload bounds, and preservation of an
existing valid JPEG after any failure. For every fake exception containing
`secret-token` or a raw body, assert the public exception and job error omit both.

- [ ] **Step 3: Confirm RED**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_cloudflare_image_provider.py -v
```

Expected: import failure for `CloudflareImageProvider`.

- [ ] **Step 4: Implement the injected provider and stable prompt contract**

Create protocol method
`CloudflareImageClient.run(*, model: str, payload: dict[str, object]) -> dict[str,
object]`. Create `CloudflareImageProvider` with class fields `provider = "cloudflare"`
and `output_extension = "jpg"`, constructor arguments `store`, `client`, model default
`@cf/black-forest-labs/flux-1-schnell`, and `steps=4`, plus synchronous method
`generate(scene: dict[str, Any], output_path: str) -> dict[str, Any]`.

Compose the visual bible plus title, prompt, and narration. Normalize whitespace and
truncate only the narration portion so the final UTF-8 prompt is at most 2,048
characters. Derive a positive 31-bit seed from SHA-256 of model, scene ID, and prompt.
Call the client, strictly Base64-decode `result.image`, validate JPEG bytes before
publication, then atomically publish through `ArtifactStore.publish_bytes_set`.

- [ ] **Step 5: Implement the bounded REST client**

Add `CloudflareRESTImageClient(account_id, api_token, timeout_seconds=60,
max_response_bytes=16_000_000)`. Use `urllib.request.Request` with JSON body and Bearer
authorization. Read at most `max_response_bytes + 1`; reject oversized payloads.
Parse the standard `{success, result, errors}` envelope.

Map socket timeout, `URLError`, HTTP 429, and HTTP 5xx to sanitized
`RetryableProviderError`. Map other HTTP 4xx, non-JSON, unsuccessful envelopes, and
schema failures to sanitized `PermanentProviderError`. Never interpolate exception
bodies, account IDs, tokens, prompts, or Cloudflare error messages into public errors.

- [ ] **Step 6: Run tests and commit**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_cloudflare_image_provider.py -v
python -m unittest discover apps/orchestrator/tests
git diff --check
git add apps/orchestrator/src/app/providers/cloudflare_image.py apps/orchestrator/tests/test_cloudflare_image_provider.py
git commit -m "feat: add Cloudflare Flux image provider"
```

### Task 3: Environment Selection and Pipeline Wiring

**Files:**
- Modify: `apps/orchestrator/src/app/services/config.py`
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Modify: `apps/orchestrator/tests/test_provider_config.py`
- Modify: `apps/orchestrator/tests/test_cli.py`
- Modify: `apps/orchestrator/tests/test_end_to_end.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing image configuration tests**

Test `build_image_provider(store, environ)` for local default, Cloudflare construction,
missing account ID, missing token, unknown provider, invalid steps, and sanitized errors.
Patch `CloudflareRESTImageClient` so tests never import credentials into a request.

Add a CLI subprocess test with `IMAGE_PROVIDER=unknown-but-unused-before-approval` and
assert `resume` at the script gate still exits zero. Set both `IMAGE_PROVIDER=local` and
`TTS_PROVIDER=local` in every subprocess test that proceeds after approval.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_provider_config.py apps/orchestrator/tests/test_cli.py -v
```

Expected: missing `build_image_provider` and no Cloudflare injection.

- [ ] **Step 3: Implement image environment construction**

Add:

```python
def build_image_provider(store: ArtifactStore, environ: Mapping[str, str]):
    provider = environ.get("IMAGE_PROVIDER", "local").strip().lower()
    if provider == "local":
        return LocalImageProvider(store)
    if provider != "cloudflare":
        raise ValueError("IMAGE_PROVIDER must be 'local' or 'cloudflare'")
    account_id = environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    model = environ.get(
        "CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell"
    ).strip()
    if not account_id or not api_token:
        raise PermanentProviderError("Cloudflare image credentials are required")
    try:
        steps = int(environ.get("CLOUDFLARE_IMAGE_STEPS", "4"))
    except ValueError as error:
        raise ValueError("CLOUDFLARE_IMAGE_STEPS must be an integer") from error
    if not 1 <= steps <= 8 or not model:
        raise ValueError("Cloudflare image model and steps are invalid")
    client = CloudflareRESTImageClient(account_id, api_token)
    return CloudflareImageProvider(store, client, model=model, steps=steps)
```

Construct the REST client only after all fields validate. Public errors name missing
environment variables but never their values.

- [ ] **Step 4: Inject both providers only after approval**

In `_build_pipeline_runner`, reuse the existing `needs_tts` approval check as
`needs_external_media`. When true, build image and TTS providers from `os.environ` and
pass both into `PipelineRunner`. Before approval, pass `None` for both so invalid or
missing live credentials cannot block the script gate.

Update `.env.example` with local defaults, empty Cloudflare credentials, model, steps,
and comments stating that deterministic tests require local providers.

- [ ] **Step 5: Verify configuration and local end-to-end behavior**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_provider_config.py apps/orchestrator/tests/test_cli.py apps/orchestrator/tests/test_end_to_end.py -v
python -m unittest discover apps/orchestrator/tests
git diff --check
```

Expected: local CLI-to-MP4 remains deterministic and no test makes a network call.

- [ ] **Step 6: Commit environment wiring**

```powershell
git add .env.example apps/orchestrator/src/app/services/config.py apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_provider_config.py apps/orchestrator/tests/test_cli.py apps/orchestrator/tests/test_end_to_end.py
git commit -m "feat: select scene image provider from environment"
```

### Task 4: Safe Cloudflare Image Smoke Command

**Files:**
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Create: `apps/orchestrator/tests/test_cloudflare_image_smoke.py`

- [ ] **Step 1: Write failing smoke-command tests**

Call `_smoke_cloudflare_image` with an injected fake client. Assert it writes a JPEG
under `tmp/` and stdout contains exactly:

```python
{"model", "seed", "steps", "width", "height", "mime_type", "output_path"}
```

Assert stdout/stderr omit prompt, account ID, token, and raw response. Test rejection of
absolute paths, traversal, non-`tmp/` paths, non-`.jpg` suffixes, empty prompt, missing
credentials before client construction, and exact retry count for retryable failures.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_cloudflare_image_smoke.py -v
```

Expected: `_smoke_cloudflare_image` and parser command do not exist.

- [ ] **Step 3: Implement parser, bounded smoke retry, and sanitized JSON**

Add `smoke-cloudflare-image` with required `--prompt` and default
`tmp/cloudflare-image-smoke.jpg`. Always construct Cloudflare regardless of
`IMAGE_PROVIDER`. Validate credentials and output before client construction. Retry only
`RetryableProviderError` up to `CLOUDFLARE_IMAGE_MAX_ATTEMPTS` (default 3), with bounded
delays of 1, 2 seconds. Validate the published file and print only the approved metadata
fields.

- [ ] **Step 4: Run tests and commit**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest apps/orchestrator/tests/test_cloudflare_image_smoke.py -v
python -m unittest discover apps/orchestrator/tests
git diff --check
git add apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_cloudflare_image_smoke.py
git commit -m "feat: add safe Cloudflare image smoke command"
```

### Task 5: Live Acceptance, Documentation, and Delivery

**Files:**
- Create: `goals/cloudflare-ai-images.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `.gitignore` only if live checkpoint names are not already covered

- [ ] **Step 1: Configure credentials without exposing them**

Have the user create a Cloudflare API token with Workers AI read/run permission and put
`CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in ignored `.env`. Verify only
boolean presence and `git check-ignore`; never print values.

- [ ] **Step 2: Run one live image smoke request**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m app smoke-cloudflare-image --prompt "cinematic illustrated Thai folktale river spirit, no text" --output tmp/cloudflare-image-smoke.jpg
```

Confirm exit zero, `image/jpeg`, dimensions within bounds, a non-empty file, and no
credential or prompt in terminal output.

- [ ] **Step 3: Run a real short project through final approval**

Create a new project and run to script approval without Cloudflare construction. Approve
the script, then resume with `IMAGE_PROVIDER=cloudflare` and `TTS_PROVIDER=google`.
Confirm every image job has provider `cloudflare`, model
`@cf/black-forest-labs/flux-1-schnell`, `.jpg` output, `image/jpeg`, and validated files.
Confirm `voice_provider=google`, 24 kHz narration, a real MP4, passing QA, final approval
pause, and dashboard export containing the project.

- [ ] **Step 4: Document setup, limits, recovery, and safety**

Document token creation at a high level, all environment variables, smoke command,
10,000-neuron daily Free allocation, Flux pricing/step bounds, prompt continuity limits,
center cropping, retry/checkpoint behavior, no automatic fallback, local test defaults,
and credential rotation. Record exact live evidence in `goals/cloudflare-ai-images.md`
without secrets or raw API bodies.

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

Expected: all suites and builds exit zero; only intentional documentation changes remain
before the final commit.

- [ ] **Step 6: Commit documentation and perform final review**

```powershell
git add README.md AGENTS.md goals/cloudflare-ai-images.md .gitignore
git commit -m "docs: document Cloudflare AI image workflow"
```

Review the complete diff from `main` for credential leakage, quota-triggering tests,
retry multiplication, checkpoint regressions, and format assumptions. Fix all critical
or important findings and rerun the complete verification suite.

- [ ] **Step 7: Merge, verify on main, push, and clean up**

Merge `cloudflare-ai-images` into `main` with a merge commit, rerun the complete suite on
the merged result, push `main` to `origin`, verify local and remote commit IDs match,
then remove only worktrees and branches created for this goal.
