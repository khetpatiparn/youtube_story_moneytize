# YouTube Story Automation

POC for a recoverable YouTube story automation workflow. The current build includes the repo baseline and an initial Python orchestrator skeleton.
The orchestrator now includes SQLite checkpoint/resume support and deterministic fake LLM, image, and TTS provider contracts.

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
