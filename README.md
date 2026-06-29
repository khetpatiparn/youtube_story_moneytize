# YouTube Story Automation

POC for a recoverable YouTube story automation workflow. The current build includes the repo baseline, a Python orchestrator skeleton, SQLite checkpoint/resume support, deterministic fake provider contracts, static approval/reporting artifacts, and a static Remotion renderer.

## Current Orchestrator Commands

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest discover apps/orchestrator/tests
python -m app create --topic "A river spirit teaches patience" --duration 180 --profile simple_story_th
python -m app status --project-id project_001
python -m app run --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite
python -m app resume --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite
python -m app approve-script --project-id project_001 --approved --reviewer human --notes "Script ready"
python -m app approve-final --project-id project_001 --changes-requested --reviewer human --notes "Adjust audio"
python -m app report --project-id project_001 --video-path render/story.mp4 --quality-score 0.91 --issue "No final approval yet"
```

Generated project runtime data goes under `projects/`; checkpoint data goes under `data/`. Approval decisions, contact sheets, quality reports, and project reports are written under `projects/{project_id}/reports/`.

## Current Renderer Commands

```powershell
npm.cmd install
npm.cmd run test:renderer
npm.cmd run render:sample
```

The sample renderer reads `apps/renderer/sample/render_payload.json` and writes `renders/sample.mp4`. Render outputs are ignored by Git.

## Current Dashboard Commands

```powershell
npm.cmd run test:dashboard
npm.cmd run prepare:dashboard-data
npm.cmd run dev:dashboard
npm.cmd run build:dashboard
```

The Media QA dashboard lives in `apps/dashboard/`. The data export step reads local project data from `projects/{project_id}/` when available and writes `apps/dashboard/public/dashboard-data.json`; when no generated projects exist it writes bundled demo data. The first dashboard slice is read-only.
