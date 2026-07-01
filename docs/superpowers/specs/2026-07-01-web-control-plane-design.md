# Web Control Plane Design

## Goal

Make the complete local video-production workflow usable from a web browser after the user double-clicks one launcher file. The browser must support project creation, provider configuration, script review, media generation, live progress, recovery, final review, and MP4 download. YouTube upload is not included.

## User Experience

The user double-clicks `Start YouTube Studio.bat`. The launcher starts the local API and worker, waits for the health check, and opens the dashboard in the default browser. The user does not need to open a terminal.

The primary workflow is:

1. Create a project from a topic, duration, language, story style, and profile.
2. Generate a scene-based script.
3. Review or edit the script and image prompts.
4. Approve the script before any paid or quota-consuming media generation.
5. Generate images and narration while monitoring every scene.
6. Render the MP4.
7. Review, selectively retry, re-render, and download the result.

The application restores project state from checkpoints after a browser refresh, service restart, or machine restart.

## Scope

### Included

- One-click Windows launcher that opens the local web application.
- Browser-based project creation and project management.
- Browser-based provider and API-key settings.
- Script generation, editing, change requests, and approval.
- Live project, stage, scene, retry, and error status.
- Image, narration, and final-video previews.
- Background execution, graceful cancellation, retry, and checkpoint resume.
- Selective scene regeneration and invalidation of affected downstream assets.
- Render, final review, re-render, and MP4 download.

### Excluded

- YouTube upload, channel management, and scheduled publishing.
- Remote hosting, multi-user access, and access from other devices.
- A packaged Electron or Tauri desktop application.
- Unbounded automatic retries or silent fallback to another paid provider.

## Architecture

The existing Python orchestration pipeline remains the source of truth. The web layer calls a local API instead of duplicating pipeline behavior in React.

### Components

- **Launcher:** Starts the API and background worker, detects startup failures and port conflicts, waits for readiness, and opens the browser without leaving a terminal window in the normal path.
- **Web dashboard:** Provides projects, script review, production monitoring, final review, and settings screens.
- **Local API:** Validates requests, reads project state, accepts control commands, publishes progress, and serves validated local media.
- **Job worker:** Executes durable jobs independently of browser connections and serializes state-changing commands per project.
- **Existing pipeline:** Owns content, image, TTS, timeline, checkpoint, approval, report, and render behavior.
- **Project storage:** Retains project inputs, assets, manifests, checkpoints, logs, reports, and renders under the existing project layout.
- **Secret store:** Encrypts provider credentials for the current Windows user and never returns plaintext credentials through the API.

The API binds to `127.0.0.1`. Browser and API are same-origin in the launcher workflow. The service does not listen on LAN interfaces by default.

## Dashboard Screens

### Projects

The projects screen lists real local projects and their current stage. It supports creating a project, opening an existing project, making a copy, and deleting a project only after explicit confirmation. Project creation collects topic, target duration, language, story style, and channel profile.

### Script Review

The script screen displays scenes with timings, narration, and image prompts. The user can edit fields directly, request an AI revision with instructions, or approve the script. Media generation cannot start before script approval.

If an approved script is edited later, the application identifies affected scenes and marks only their dependent media and render artifacts stale.

### Production Monitor

The production screen shows overall stage progress and per-scene states such as queued, generating image, generating narration, ready, failed, or cancelled. Each scene exposes its script excerpt, image prompt, image preview, audio preview, attempt count, and sanitized error summary.

Progress updates automatically. The initial implementation may use short polling behind a stable progress interface; the API can later switch to server-sent events without changing pipeline state contracts.

### Final Review

The final screen plays the rendered MP4 in the browser and supports download, re-render, final approval, change requests, and selective scene regeneration. Reusing validated assets is the default; unchanged scenes are not regenerated.

### Settings

The settings screen configures content, image, and TTS providers, API keys, render quality, retry bounds, and the projects directory. A credential can be saved, replaced, removed, or tested with an explicit smoke action. The UI reveals only configured status and a short masked suffix.

## API and State Model

The current dashboard control endpoints remain compatible and are extended with resources for project creation, settings, jobs, scene details, edits, cancellation, media access, and downloads.

State-changing endpoints return a durable job identifier rather than holding the request open for the full operation. Job state includes project, operation, stage, scene where applicable, timestamps, progress, attempt count, cancellation state, and a sanitized error code and message.

Only one state-changing job may run per project. Duplicate requests are rejected deterministically. Read operations remain available while a job is running.

The pipeline writes checkpoints and artifacts atomically where supported. The API derives displayed state from durable project state rather than browser memory.

## Asset Invalidation

Inputs and generated outputs carry fingerprints. Editing script or prompt inputs marks only dependent scene media stale. Replacing narration invalidates the scene timing and final render. Replacing an image invalidates the final render but not narration. A new artifact is published only after validation succeeds; the last valid artifact remains recoverable until replacement completes.

## Error Handling and Recovery

- Provider retries remain finite and distinguish transient from permanent failures.
- Errors identify the project stage and scene without exposing credentials, full provider bodies, or sensitive request content.
- Retry targets the failed job or selected scene rather than restarting the whole project.
- Graceful cancellation stops at a safe boundary and preserves the latest valid checkpoint.
- Restarting the application reconciles interrupted jobs and offers resume where safe.
- Launcher failures explain missing dependencies, unavailable ports, invalid configuration, and service startup failures in actionable language.

## Security

- Bind control and media endpoints to loopback only.
- Encrypt credentials using Windows user-bound protection; do not store plaintext keys in project files or browser storage.
- Never return a stored credential through the API after submission.
- Redact credentials and sensitive provider payloads from logs and errors.
- Validate project identifiers, contained paths, filenames, MIME types, extensions, and response sizes.
- Exclude credentials from project copy, export, reports, and downloads.
- Keep live provider smoke calls explicit so ordinary tests and page loads cannot consume quota.

## Delivery Slices

### Slice 1: Web project creation and settings

Add the launcher foundation, encrypted local settings, provider configuration, project creation, and real project listing. The user can start the application and create a configured project without a terminal.

### Slice 2: Script review and live production monitor

Add durable background jobs, script generation and editing, script approval, progress reporting, per-scene visibility, cancellation, retry, and resume.

### Slice 3: Final production and download

Add selective scene regeneration, rendering, in-browser final review, final approval and change requests, re-render, validated media serving, MP4 download, and full launcher acceptance coverage.

Each slice must be independently tested and leave existing CLI behavior operational for diagnostics and automated testing, even though normal user operation moves to the browser.

## Testing

- Unit tests for settings encryption adapters, validation, job state, locking, state transitions, invalidation, and error redaction.
- API tests for every read and mutation, including duplicate jobs, invalid paths, cancellation, retry, and resume.
- Dashboard tests for project creation, settings, script approval, progress, failures, retries, final review, and downloads.
- Deterministic integration tests with local content, image, and TTS providers.
- A browser-to-MP4 acceptance test that creates a project through the API/UI path and downloads a valid render.
- Explicit live smoke commands for Gemini and Cloudflare only; the default suite continues to force local providers.

## Completion Criteria

The feature is complete when a user on the supported Windows environment can double-click one launcher, configure providers, create a project, approve its script, observe media generation scene by scene, recover from a controlled failure, render the project, preview the result, and download the MP4 without entering a CLI command.
