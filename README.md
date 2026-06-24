# YouTube Story Automation

POC for a recoverable YouTube story automation workflow. The current build includes the repo baseline, a Python orchestrator skeleton, SQLite checkpoint/resume support, deterministic fake provider contracts, and a static Remotion renderer.

## Current Orchestrator Commands

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest discover apps/orchestrator/tests
python -m app create --topic "A river spirit teaches patience" --duration 180 --profile simple_story_th
python -m app status --project-id project_001
python -m app run --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite
python -m app resume --project-id project_001 --checkpoint-db ./data/checkpoints.sqlite
```

Generated project runtime data goes under `projects/`; checkpoint data goes under `data/`. Both generated paths are ignored by Git.

## Current Renderer Commands

```powershell
npm.cmd install
npm.cmd run test:renderer
npm.cmd run render:sample
```

The sample renderer reads `apps/renderer/sample/render_payload.json` and writes `renders/sample.mp4`. Render outputs are ignored by Git.
