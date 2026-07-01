# Cloudflare AI Scene Images

Status: implementation and live acceptance complete; final verification and delivery in progress

## Outcome

Deliver an opt-in Cloudflare Workers AI image workflow that creates one validated Flux JPEG per approved scene and renders those images with configured narration, while keeping the default local pipeline deterministic and quota-free.

## Completed implementation checkpoints

- [x] Provider-neutral SVG and JPEG validation with contained artifact paths.
- [x] Cloudflare Flux provider with sanitized failures and atomic JPEG publication.
- [x] Environment-based local or Cloudflare provider selection after script approval.
- [x] Bounded transient retry and checkpoint/resume reuse of valid scene images.
- [x] Safe explicit `smoke-cloudflare-image` command restricted to `tmp/*.jpg`.
- [x] Renderer support for JPEG assets using a centered cover crop.
- [x] Setup, security, recovery, quota, and limitation documentation.

## Acceptance evidence still required

- [x] Intentional live Cloudflare smoke generated a validated 1024×1024 Flux JPEG at 4 steps.
- [x] Credentialed `cloudflare_ai_sample` reached final approval with three Cloudflare JPEGs and Gemini narration.
- [x] Render payload, MP4, reports, and dashboard data prove the sample uses Cloudflare images.
- [x] Full orchestrator (149 tests, 1 Windows symlink skip), renderer (5 tests), dashboard
  (10 tests), end-to-end, dashboard production build, compile, and `git diff --check`
  verification pass.
- [x] Implementation, spec, code-quality, live-regression, and final inline review findings are resolved.
- [ ] The feature branch is merged into `main`.
- [ ] Merged `main` is reverified, pushed to `origin`, and local/remote commit IDs match.

## Safety and recovery

Secrets live only in ignored `.env`; logs, reports, errors, commits, and smoke output must not contain credentials. Default tests explicitly select local image and TTS providers. There is no automatic paid-provider fallback. Preserve `projects/{project_id}/images/jobs.json`, generated assets, and the checkpoint database after a failure; correct the configuration or quota issue and resume instead of deleting recovery state.

Character continuity is prompt-only in this slice. A successful run proves valid AI-generated scene assets and pipeline integration, not identical character identity across scenes.

## Live acceptance evidence

- Smoke: model `@cf/black-forest-labs/flux-1-schnell`, seed `1673635947`, 4 steps,
  JPEG 1024×1024.
- Scene jobs: all three completed on the first attempt with provider `cloudflare`,
  MIME `image/jpeg`, and 1024×1024 files sized 642,123, 552,251, and 388,951 bytes.
- Narration: provider `google`, mono PCM16 WAV at 24 kHz, duration 53.64 seconds.
- Render: `render/story.mp4`, 19,693,492 bytes; media QA passed with score 1.0 and
  the pipeline paused at final approval.
- Dashboard export loaded `cloudflare_ai_sample` with all three `.jpg` scene paths.
- The first live resume exposed a renderer SVG-only allowlist. Regression tests were
  added and the renderer plus QA validator now accept validated JPEG scene assets;
  resume reused the completed scene jobs rather than spending image quota again.
