# YouTube Story Automation

POC for a recoverable YouTube story automation workflow. The current build includes the repo baseline and an initial Python orchestrator skeleton.

## Current Orchestrator Commands

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest discover apps/orchestrator/tests
python -m app create --topic "A river spirit teaches patience" --duration 180 --profile simple_story_th
python -m app status --project-id project_001
python -m app run --project-id project_001
```

Generated project runtime data goes under `projects/` and is ignored by Git.
