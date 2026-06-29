# YouTube Story Automation

POC for a recoverable YouTube story automation workflow. The local path now runs end to end without API credentials: deterministic content, SVG scenes, WAV narration, SQLite checkpoints, two human approval gates, runtime Remotion rendering, media QA reports, and the read-only dashboard.

## Current Orchestrator Commands

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest discover apps/orchestrator/tests
python -m app create --project-id sample_story --topic "A river spirit teaches patience" --duration 30 --profile simple_story_th
python -m app run --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-script --project-id sample_story --approved --reviewer human --checkpoint-db ./data/checkpoints.sqlite
python -m app resume --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-final --project-id sample_story --approved --reviewer human --checkpoint-db ./data/checkpoints.sqlite
python -m app resume --project-id sample_story --checkpoint-db ./data/checkpoints.sqlite
python -m app status --project-id sample_story
python -m app report --project-id project_001 --video-path render/story.mp4 --quality-score 0.91 --issue "No final approval yet"
```

The first `run` stops at script approval. The first `resume` after approval generates images and narration, renders the MP4, validates it, writes reports, and stops at final approval. The last `resume` changes the project to `completed`. Use `--tts-words-per-second 1000` on `resume` only for a fast one-second smoke render; the normal default is `2.5`.

Generated runtime data goes under `projects/{project_id}/`: outline and script in `content/`, scene JSON in `scenes/`, SVGs in `images/`, WAV in `audio/`, payload and MP4 in `render/`, and approvals/quality/contact/project reports in `reports/`. Checkpoint data goes under `data/`.

Resume is idempotent. Completed images, audio, renders, and reports are fingerprinted or validated before reuse. A failed render remains at `render_ready`; fix the cause and run `resume` again. Image retry is limited to three total attempts per failed scene by default (`--max-image-attempts` changes the bound).

## Local Provider Limitations

- Story content is deterministic template output, not a production LLM response.
- Images are deterministic SVG review assets, not production illustrations or character-consistent art.
- Narration is synthetic tones in a valid WAV, not natural speech.
- External LLM, image, and TTS adapters still require implementation, credentials, quota handling, and provider-specific validation.
- YouTube upload, publishing, analytics, and fully autonomous operation are not implemented.

## Current Renderer Commands

```powershell
npm.cmd install
npm.cmd run test:renderer
npm.cmd run render:sample
```

The static sample command reads `apps/renderer/sample/render_payload.json`. The orchestrator uses runtime props and stages validated project assets before writing `projects/{project_id}/render/story.mp4`. Render outputs are ignored by Git.

## Current Dashboard Commands

```powershell
npm.cmd run test:dashboard
npm.cmd run prepare:dashboard-data
npm.cmd run dev:dashboard
npm.cmd run build:dashboard
```

The Media QA dashboard lives in `apps/dashboard/`. The data export step reads local project data from `projects/{project_id}/` when available and writes `apps/dashboard/public/dashboard-data.json`; when no generated projects exist it writes bundled demo data. The first dashboard slice is read-only.
