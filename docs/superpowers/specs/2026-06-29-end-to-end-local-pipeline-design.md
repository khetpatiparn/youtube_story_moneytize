# End-to-End Local Pipeline Design

## Goal

Build a deterministic local implementation of the planned YouTube Story Automation
workflow. A user must be able to create a project, run it to the script approval
gate, approve it, resume through media generation and a real Remotion render, review
the reports, approve the final video, and observe a completed project. No external
API key is required for this POC path.

## Scope and Delivery Boundaries

The implementation covers topic, outline, script, script approval, scene planning,
image generation, bounded per-scene retry, narration, timeline, render payload,
Remotion rendering, quality reports, and final approval. Existing project storage,
SQLite checkpointing, approval reporting, renderer contracts, and dashboard loading
remain the integration boundaries.

YouTube publishing, production provider credentials, advanced image consistency,
forced audio alignment, and retention analytics remain outside this POC. External
providers will implement the same interfaces later; they are not silently invoked
or treated as verified by local tests.

## Architecture

The orchestrator owns a serial, resumable state machine. Each node has one artifact
responsibility and is idempotent: it reads persisted inputs, writes its output
atomically, and records the next stage. The workflow service decides whether to run
a node, stop at an approval gate, retry a failed scene, or complete the project.
SQLite stores a full state snapshot after every successful transition. Project files
remain the source of reviewable artifacts and the dashboard's read model.

The POC uses explicit Python control flow instead of depending on LangGraph being
installed. The graph-facing API remains compatible with the existing state schema,
so a later LangGraph adapter can map the same node transitions without changing
providers or artifact formats.

## Components

### Workflow Service

`PipelineRunner` loads metadata and the latest checkpoint, validates the stored
stage, executes eligible nodes in order, and persists after each transition. It
returns a structured result with `status`, `current_node`, and `waiting_for`. The CLI
uses the same service for both `run` and `resume`; `resume` differs only by requiring
an existing checkpoint.

The states are:

1. `created`
2. `content_ready`
3. `awaiting_script_approval`
4. `media_ready`
5. `render_ready`
6. `awaiting_final_approval`
7. `completed`

A rejected script returns to content generation with an incremented script version.
A rejected final review remains at the final gate and records the requested changes;
automatic creative revision is not claimed in this POC.

### Deterministic Providers

The local LLM provider derives a stable outline, script, and scene list from the
topic, duration, language, and profile. Outputs are stable for identical inputs and
include the existing prompt hash metadata.

The local image provider writes a valid SVG for each scene using deterministic color,
title, and composition values derived from the prompt hash. It can inject configured
failures for tests. Every image job stores its attempt count and terminal status.
Only failed scene IDs are retried, with three total attempts by default. Exhaustion
stops the pipeline with an actionable error and leaves the last checkpoint intact.

The local TTS provider writes a valid mono PCM WAV containing deterministic tones and
silence sized from the script. This is deliberately synthetic narration, not natural
speech. It proves the audio and timing pipeline while keeping the POC credential-free.

### Timeline and Renderer

The timeline builder reads the actual WAV duration and divides it across scenes using
scene narration word counts, correcting the final scene so the total frames exactly
match the audio duration at the configured FPS. It writes
`render/render_payload.json` using the existing renderer contract.

Generated SVG files and WAV audio are staged under the renderer public directory or
otherwise copied into Remotion's supported static-file root. The render service calls
the repository's pinned Remotion CLI command with the project payload and writes
`render/story.mp4`. Exit code, stderr, output existence, and non-zero file size are
validated. Paths stored in project JSON remain project-relative and are rejected if
absolute or traversing.

The Remotion composition must accept runtime input props rather than importing only
the bundled sample payload. It renders scene sequences and includes the narration
audio track when `audioPath` is present.

### Quality and Approval Gates

Quality validation confirms that all scenes have images, timeline ranges are ordered
and contiguous, the WAV and MP4 exist and are non-empty, and rendered duration is
within one frame of the payload duration. It produces a score from deterministic
checks and a concrete issue list. The existing reporting service writes
`quality_report.json`, `contact_sheet.md`, and `project_report.md`.

The script gate requires an approved script decision before media nodes can run. The
final gate requires an approved final decision before status becomes `completed`.
Approval commands update their existing JSON file and immediately synchronize the
workflow checkpoint so a subsequent process can resume correctly.

## Artifact Contract

Each project uses these reviewable paths:

- `metadata.json`
- `content/outline.json`
- `content/script.txt`
- `scenes/scenes.json`
- `images/{scene_id}.svg`
- `audio/narration.wav`
- `render/render_payload.json`
- `render/story.mp4`
- `reports/approvals.json`
- `reports/quality_report.json`
- `reports/contact_sheet.md`
- `reports/project_report.md`

Writes use temporary sibling files followed by replacement where partial output
would make resume ambiguous. Checkpoint state stores artifact-relative paths, node
status, script version, image attempt counts, and failed scene IDs.

## Error Handling and Recovery

Input and persisted paths are constrained to the selected project directory. Invalid
JSON, missing required artifacts, impossible state transitions, and subprocess
failures stop with a non-zero CLI result and a specific message. Completed nodes are
not repeated on resume. Retry applies only to declared transient image failures and
never loops without a configured bound. A failed render may be retried once by a new
`resume` invocation; it is not retried endlessly inside one run.

The project checkpoint is saved only after a node's artifacts validate. If a process
stops between an atomic artifact write and checkpoint persistence, the node safely
revalidates and overwrites the deterministic artifact on resume.

## CLI Flow

The supported demonstration is:

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m app create --project-id sample_story --topic "A river spirit teaches patience" --duration 30 --profile simple_story_th
python -m app run --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-script --project-id sample_story --approved --reviewer human
python -m app resume --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-final --project-id sample_story --approved --reviewer human
python -m app resume --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app status --project-id sample_story
```

The first run must stop at script approval. The first resume after approval must
produce media, render, and reports, then stop at final approval. The final resume
must report `completed` without regenerating prior artifacts.

## Testing Strategy

Unit tests cover every state transition, deterministic provider contract, atomic
artifact write, path constraint, timeline frame calculation, image retry bound, and
quality check. Integration tests use temporary project directories and a subprocess
stub only where isolating Remotion failure behavior is required.

An end-to-end test uses the real CLI, local providers, SQLite, and Remotion to produce
a short MP4. It asserts both approval pauses, restart-based resume, expected artifact
paths, non-empty WAV and MP4 files, final completed state, and dashboard live-project
loading. Renderer and dashboard contract suites remain separate regression gates.

## Acceptance Criteria

- The documented CLI sequence completes without external credentials.
- Script and final approval gates stop and resume across separate processes.
- Failed image scenes retry independently and stop after the configured maximum.
- Timeline frames are derived from the generated WAV and cover every scene once.
- Remotion consumes the generated runtime payload and writes a real MP4 with audio.
- Reports and dashboard data describe the generated project rather than demo data.
- All orchestrator, renderer, dashboard, and end-to-end tests pass.
- Dashboard production build and `git diff --check` pass.
- README and AGENTS explain commands, recovery, local-provider limitations, and the
  fact that production external providers and YouTube upload remain unimplemented.
