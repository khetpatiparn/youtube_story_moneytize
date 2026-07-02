# Web Control Plane Slice 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run script generation as a durable background job, edit and approve the script in the browser, and monitor per-stage and per-scene production with cancel, retry, and resume.

**Architecture:** Introduce a SQLite-backed job repository and one in-process worker queue. API mutations enqueue jobs and return `202` immediately; browser polling reads durable status through a standard query/state library rather than handwritten polling state. Pipeline callbacks publish sanitized stage and scene progress without changing provider contracts.

**Tech Stack:** Python `sqlite3`, `threading`, existing checkpoint pipeline, React 19, TanStack Query, Node test runner.

---

### Task 1: Durable job model and repository

**Files:**
- Create: `apps/orchestrator/src/app/schemas/job.py`
- Create: `apps/orchestrator/src/app/repositories/job_repository.py`
- Create: `apps/orchestrator/tests/test_job_repository.py`

- [ ] **Step 1: Write failing tests for enqueue, uniqueness, transitions, and restart reads**

```python
def test_one_active_job_per_project(self):
    first = self.jobs.enqueue("project_001", "run")
    with self.assertRaisesRegex(ValueError, "active job"):
        self.jobs.enqueue("project_001", "resume")
    self.jobs.finish(first.job_id, status="succeeded")
    self.assertEqual(self.jobs.enqueue("project_001", "resume").status, "queued")
```

- [ ] **Step 2: Run tests and verify missing-module failure**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_job_repository.py`

- [ ] **Step 3: Implement `JobRecord` and SQLite repository**

Use states `queued`, `running`, `cancelling`, `cancelled`, `succeeded`, and `failed`. Persist operation, project ID, optional scene ID, progress `0..1`, stage, attempts, timestamps, sanitized error code/message, and cancellation request. Enforce one active job per project with a partial unique SQLite index over active states.

- [ ] **Step 4: Run repository and checkpoint tests**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_job_repository.py apps/orchestrator/tests/test_checkpoint_repository.py`

- [ ] **Step 5: Commit durable jobs**

```powershell
git add apps/orchestrator/src/app/schemas/job.py apps/orchestrator/src/app/repositories/job_repository.py apps/orchestrator/tests/test_job_repository.py
git commit -m "feat: add durable dashboard jobs"
```

### Task 2: Background worker and sanitized failures

**Files:**
- Create: `apps/orchestrator/src/app/services/job_worker.py`
- Create: `apps/orchestrator/src/app/services/error_sanitizer.py`
- Create: `apps/orchestrator/tests/test_job_worker.py`

- [ ] **Step 1: Write failing worker tests**

```python
def test_worker_returns_immediately_and_records_result(self):
    job = self.jobs.enqueue("project_001", "run")
    self.worker.process_one()
    self.assertEqual(self.jobs.get(job.job_id).status, "succeeded")

def test_provider_failure_redacts_secret(self):
    self.actions.run_project.side_effect = RuntimeError("token AQ.secret failed")
    job = self.jobs.enqueue("project_001", "run")
    self.worker.process_one()
    self.assertNotIn("AQ.secret", self.jobs.get(job.job_id).error_message)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_job_worker.py`

- [ ] **Step 3: Implement bounded worker dispatch**

```python
OPERATIONS = {"run": "run_project", "resume": "resume_project"}

def process_one(self) -> bool:
    job = self.jobs.claim_next()
    if job is None:
        return False
    try:
        result = getattr(self.actions, OPERATIONS[job.operation])(job.project_id)
        self.jobs.finish(job.job_id, "succeeded", progress=1.0, stage=result.get("currentNode"))
    except Exception as error:
        code, message = sanitize_error(error, self.secret_values())
        self.jobs.finish(job.job_id, "failed", error_code=code, error_message=message)
    return True
```

Run a daemon worker thread with an event wake-up and a one-second idle wait. On startup, change orphaned `running` jobs to `failed` with code `application_restarted`; the UI offers resume. Cancellation is cooperative through a callback checked between pipeline nodes and scene attempts.

Do not introduce Celery, Redis, or another external queue for this slice. The local browser-first requirement favors a zero-extra-infra worker that starts with the existing launcher.

- [ ] **Step 4: Run worker tests**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_job_worker.py`

- [ ] **Step 5: Commit worker**

```powershell
git add apps/orchestrator/src/app/services/job_worker.py apps/orchestrator/src/app/services/error_sanitizer.py apps/orchestrator/tests/test_job_worker.py
git commit -m "feat: run dashboard jobs in background"
```

### Task 3: Job API and polling contracts

**Files:**
- Modify: `apps/orchestrator/src/app/http/dashboard_api.py`
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Modify: `apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 1: Add failing tests for enqueue, list, detail, cancel, duplicate, and unknown job**

```python
def test_run_returns_accepted_job(self):
    response = self.request("POST", "/api/projects/project_001/run")
    self.assertEqual(response.status, 202)
    self.assertEqual(response.json["job"]["status"], "queued")

def test_cancel_marks_job_cancelling(self):
    response = self.request("POST", f"/api/jobs/{self.job_id}/cancel")
    self.assertEqual(response.json["job"]["status"], "cancelling")
```

- [ ] **Step 2: Run API tests and verify synchronous-contract failures**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 3: Replace synchronous run/resume routing with job submission**

Add `GET /api/jobs?projectId=...`, `GET /api/jobs/{jobId}`, and `POST /api/jobs/{jobId}/cancel`. Keep approval writes synchronous because they are short and atomic. Return `409` with active job metadata for duplicate project mutations. Inject jobs and worker in `_run_dashboard_api` and stop the worker in server shutdown.

- [ ] **Step 4: Run API and CLI tests**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_control_api.py apps/orchestrator/tests/test_cli.py`

- [ ] **Step 5: Commit job API**

```powershell
git add apps/orchestrator/src/app/http/dashboard_api.py apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_dashboard_control_api.py
git commit -m "feat: expose background job controls"
```

### Task 4: Script read, edit, and approval contracts

**Files:**
- Create: `apps/orchestrator/src/app/services/script_editor.py`
- Modify: `apps/orchestrator/src/app/http/dashboard_api.py`
- Create: `apps/orchestrator/tests/test_script_editor.py`
- Modify: `apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 1: Write failing tests for scene reads, atomic edits, revision conflict, and approval precondition**

```python
def test_update_rejects_stale_revision(self):
    current = self.editor.read("project_001")
    self.editor.update("project_001", current["revision"], [{"sceneId": "scene_001", "narration": "new", "prompt": "p"}])
    with self.assertRaisesRegex(ValueError, "revision"):
        self.editor.update("project_001", current["revision"], [])
```

- [ ] **Step 2: Run tests and verify missing service**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_script_editor.py`

- [ ] **Step 3: Implement fingerprinted script editing and endpoints**

Use SHA-256 of canonical JSON as `revision`. Validate at most 100 scenes; scene IDs with the existing safe identifier rule; narration `1..5000` characters; prompt `1..4000` characters. Atomically replace `scenes/scenes.json` and the script artifact only after the entire request validates. Add `GET` and `PUT /api/projects/{id}/script`; reject edits while a project job is active. Approval requires the submitted revision to match current content.

- [ ] **Step 4: Run editor and API tests**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_script_editor.py apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 5: Commit script control**

```powershell
git add apps/orchestrator/src/app/services/script_editor.py apps/orchestrator/src/app/http/dashboard_api.py apps/orchestrator/tests/test_script_editor.py apps/orchestrator/tests/test_dashboard_control_api.py
git commit -m "feat: edit and approve scripts from web"
```

### Task 5: Per-stage and per-scene progress

**Files:**
- Create: `apps/orchestrator/src/app/services/progress_reporter.py`
- Modify: `apps/orchestrator/src/app/services/pipeline_runner.py`
- Modify: `apps/orchestrator/src/app/services/image_pipeline.py`
- Modify: `apps/orchestrator/src/app/services/timeline.py`
- Modify: `apps/orchestrator/src/app/services/dashboard_control.py`
- Create: `apps/orchestrator/tests/test_progress_reporter.py`
- Modify: `apps/orchestrator/tests/test_pipeline_runner.py`

- [ ] **Step 1: Write failing callback tests**

```python
def test_scene_attempt_updates_durable_progress(self):
    reporter.scene("scene_002", "generating_image", attempt=2, progress=0.5)
    detail = jobs.get(job.job_id)
    self.assertEqual(detail.scene_progress["scene_002"]["attempt"], 2)
```

- [ ] **Step 2: Run tests and verify missing reporter**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_progress_reporter.py`

- [ ] **Step 3: Add optional progress and cancellation callbacks**

Define `ProgressReporter.stage(name, progress)` and `scene(scene_id, status, attempt, progress, error=None)`. Pass a no-op default through `PipelineRunner` so CLI callers remain unchanged. Emit updates before and after content, each image attempt, each narration item, timeline, render, quality, and approval pauses. Check `cancel_requested()` only between safe atomic operations.

- [ ] **Step 4: Run pipeline and progress tests**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_progress_reporter.py apps/orchestrator/tests/test_pipeline_runner.py apps/orchestrator/tests/test_image_pipeline.py`

- [ ] **Step 5: Commit progress instrumentation**

```powershell
git add apps/orchestrator/src/app/services/progress_reporter.py apps/orchestrator/src/app/services/pipeline_runner.py apps/orchestrator/src/app/services/image_pipeline.py apps/orchestrator/src/app/services/timeline.py apps/orchestrator/src/app/services/dashboard_control.py apps/orchestrator/tests/test_progress_reporter.py apps/orchestrator/tests/test_pipeline_runner.py
git commit -m "feat: publish scene production progress"
```

### Task 6: Script review and production monitor UI

**Files:**
- Create: `apps/dashboard/src/data/jobRequests.js`
- Create: `apps/dashboard/src/data/scriptRequests.js`
- Create: `apps/dashboard/src/components/ScriptReview.jsx`
- Create: `apps/dashboard/src/components/ProductionMonitor.jsx`
- Modify: `apps/dashboard/src/App.jsx`
- Modify: `apps/dashboard/src/styles.css`
- Create: `apps/dashboard/tests/jobRequests.test.mjs`
- Create: `apps/dashboard/tests/scriptRequests.test.mjs`
- Modify: `apps/dashboard/tests/appStatic.test.mjs`

- [ ] **Step 1: Write failing request and static component tests**

Test that polling stops on terminal job states, aborts on unmount, uses a minimum 1000 ms interval, saves a revision with edits, and includes revision in approval.

- [ ] **Step 2: Run dashboard tests and verify missing modules**

Run: `npm.cmd run test:dashboard`

- [ ] **Step 3: Implement script and monitor views**

Use TanStack Query for polling, cache invalidation, and mutation lifecycle management, with `AbortController` for request cancellation. Poll no faster than once per second and avoid overlapping requests. Show stage, percent, scene status, prompt, narration, image/audio paths, attempts, sanitized error, Cancel, Retry, and Resume. Disable edits during active jobs. Refresh project and script after terminal job state.

- [ ] **Step 4: Run dashboard tests and build**

Run: `npm.cmd run test:dashboard`

Run: `npm.cmd run build:dashboard`

Expected: all pass.

- [ ] **Step 5: Commit monitor UI and update goal evidence**

```powershell
git add apps/dashboard/src apps/dashboard/tests goals/web-control-plane.md
git commit -m "feat: add live web production monitor"
```

### Task 7: Slice 2 acceptance and recovery

**Files:**
- Create: `apps/orchestrator/tests/test_dashboard_job_acceptance.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `goals/web-control-plane.md`

- [ ] **Step 1: Add a local-provider acceptance test**

Create a project through the API, enqueue `run`, poll until script approval, edit one scene, approve the current revision, enqueue resume, cancel at a safe callback, recreate the worker, resume, and assert progress plus checkpoint survival.

- [ ] **Step 2: Run focused acceptance**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_job_acceptance.py`

Expected: pass without network requests.

- [ ] **Step 3: Run all tests and builds**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest discover apps/orchestrator/tests`

Run: `npm.cmd run test:dashboard`

Run: `npm.cmd run build:dashboard`

- [ ] **Step 4: Document progress states, recovery, and diagnostics**

Document browser behavior first and retain CLI commands only under diagnostics. Record exact acceptance evidence in the goal.

- [ ] **Step 5: Commit Slice 2 acceptance**

```powershell
git add apps/orchestrator/tests/test_dashboard_job_acceptance.py README.md AGENTS.md goals/web-control-plane.md
git commit -m "test: verify recoverable web production jobs"
```
