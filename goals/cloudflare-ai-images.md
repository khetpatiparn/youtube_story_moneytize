# Cloudflare AI Scene Images

Status: in progress

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

- [ ] Intentional live Cloudflare smoke generates and validates a real Flux JPEG.
- [ ] Credentialed sample pipeline reaches final approval with one Cloudflare JPEG per scene and Gemini narration.
- [ ] Render payload, MP4, reports, and dashboard data prove the sample uses Cloudflare images.
- [ ] Full orchestrator, renderer, dashboard, end-to-end, dashboard production build, and `git diff --check` verification pass.
- [ ] Review findings are resolved and the feature branch is merged into `main`.
- [ ] Merged `main` is reverified, pushed to `origin`, and local/remote commit IDs match.

## Safety and recovery

Secrets live only in ignored `.env`; logs, reports, errors, commits, and smoke output must not contain credentials. Default tests explicitly select local image and TTS providers. There is no automatic paid-provider fallback. Preserve `projects/{project_id}/images/jobs.json`, generated assets, and the checkpoint database after a failure; correct the configuration or quota issue and resume instead of deleting recovery state.

Character continuity is prompt-only in this slice. A successful run proves valid AI-generated scene assets and pipeline integration, not identical character identity across scenes.
