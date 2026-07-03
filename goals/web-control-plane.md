# Web Control Plane Slice 2

## Objective
Deliver a browser-first local Production Control Room with durable background jobs,
script editing and approval, live stage/scene progress, cancellation, restart recovery,
and truthful live project state.

## Delivered
- SQLite-backed run/resume jobs with one active job per project
- daemon worker lifecycle started by the dashboard API
- cooperative cancellation at safe progress boundaries; queued cancellation completes immediately
- sanitized failures, restart recovery, stage/scene context, and recent project events
- revision-safe script editing and approval
- queue rail, live production panel, control rail, and secondary script workspace
- truthful empty state with offline sample fallback only when the API is unavailable
- deterministic HTTP acceptance coverage for create, run, edit, approve, cancel, worker restart, resume, and checkpoint survival

## Verification
- `python -m unittest apps/orchestrator/tests/test_dashboard_job_acceptance.py`
- `python -m unittest apps/orchestrator/tests/test_dashboard_job_service.py apps/orchestrator/tests/test_job_repository.py apps/orchestrator/tests/test_job_worker.py apps/orchestrator/tests/test_progress_reporter.py`
- `python -m unittest discover apps/orchestrator/tests`
- `npm.cmd run test:renderer`
- `npm.cmd run test:dashboard`
- `npm.cmd run build:dashboard`
- Browser QA at `http://127.0.0.1:5173/`

## Current Evidence
- dashboard job acceptance: 1 passed
- focused background-job, cancellation, control-service, and progress suite: 36 passed
- full orchestrator suite: 250 passed, 1 skipped
- renderer node suite: 5 passed
- dashboard node suite: 40 passed
- production dashboard build: passed
- runtime health: API returned `{\"ok\":true}` and dashboard returned HTTP 200 on `127.0.0.1`

## Remaining Verification
- In-app Browser QA is pending because the Browser runtime was unavailable in this session.
- Playwright fallback was not installed and no browser dependency was added.

## Scope Boundary
- local-only control plane; no uploads or YouTube publishing
- external Gemini and Cloudflare capacity/quality require separate intentional smoke tests
- cancellation is cooperative between safe pipeline operations, not process termination during a provider request
