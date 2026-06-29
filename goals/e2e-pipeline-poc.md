# Goal: End-to-End Local POC Pipeline

## Outcome

Deliver a deterministic local workflow that turns a project topic into a reviewed
MP4 and supporting artifacts without requiring external API credentials.

## Scope

- Generate deterministic outline, script, scenes, images, and narration.
- Pause for script approval and final approval, then resume from SQLite state.
- Retry only failed image scenes with a finite attempt limit.
- Build an audio-derived timeline and Remotion payload.
- Invoke Remotion to create a real MP4.
- Validate artifacts and write quality, contact-sheet, and project reports.
- Keep provider interfaces ready for later external implementations.
- Surface the completed project in the read-only Media QA dashboard.

## Delivery Slices

1. Workflow state, artifact schemas, and deterministic content providers.
2. Script approval pause/resume and scene image generation with bounded retry.
3. Local narration, timeline construction, Remotion integration, and QA.
4. Final approval pause/resume, sample project, documentation, and full verification.

Each slice is developed on a feature branch, tested, reviewed, and committed as a
recoverable milestone before integration.

## Acceptance Evidence

- A clean checkout can create and run the documented sample project.
- The first run stops at script approval; approving and resuming reaches final approval.
- A configured test scene failure retries only that scene and never exceeds its limit.
- The project contains script, scene, image, WAV, render payload, MP4, approval, and report artifacts.
- Restarting the CLI resumes from the latest persisted workflow state without repeating completed work.
- Orchestrator, renderer, dashboard, and end-to-end tests pass.
- The dashboard production build and `git diff --check` pass.
- README and AGENTS list the commands, recovery steps, and external-provider limitations.

## Out of Scope

- YouTube upload and publishing.
- Production LLM, image, or TTS credentials and billing.
- Advanced character consistency, forced alignment, and YouTube analytics.

