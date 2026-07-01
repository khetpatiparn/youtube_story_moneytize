# Web Control Plane Slice 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support selective scene regeneration, safe media preview, rendering, final review, re-render, approval, and MP4 download entirely in the browser.

**Architecture:** Add explicit asset fingerprints and invalidation rules, validated contained-path media endpoints, and background operations for scene regeneration and render. The browser final-review screen consumes only API-issued media URLs and downloads.

**Tech Stack:** Python, SHA-256 manifests, existing Remotion renderer, `http.server`, React 19, Node test runner.

---

### Task 1: Asset fingerprints and dependency invalidation

**Files:**
- Create: `apps/orchestrator/src/app/services/asset_manifest.py`
- Create: `apps/orchestrator/tests/test_asset_manifest.py`
- Modify: `apps/orchestrator/src/app/services/artifacts.py`

- [ ] **Step 1: Write failing invalidation tests**

```python
def test_prompt_change_invalidates_image_and_render_only(self):
    result = manifest.diff_scene("scene_001", narration="same", prompt="new")
    self.assertEqual(result.stale, {"image", "render"})

def test_narration_change_invalidates_audio_timeline_and_render(self):
    result = manifest.diff_scene("scene_001", narration="new", prompt="same")
    self.assertEqual(result.stale, {"audio", "timeline", "render"})
```

- [ ] **Step 2: Run tests and verify missing module**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_asset_manifest.py`

- [ ] **Step 3: Implement canonical fingerprints and atomic manifest updates**

Hash canonical UTF-8 JSON inputs with SHA-256. Store schema version, scene input fingerprints, validated output paths and output hashes. Never delete the last valid output during invalidation; mark it stale and publish the replacement atomically before switching the manifest pointer.

- [ ] **Step 4: Run manifest and artifact tests**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_asset_manifest.py apps/orchestrator/tests/test_artifacts.py`

- [ ] **Step 5: Commit manifest support**

```powershell
git add apps/orchestrator/src/app/services/asset_manifest.py apps/orchestrator/src/app/services/artifacts.py apps/orchestrator/tests/test_asset_manifest.py
git commit -m "feat: track asset dependency fingerprints"
```

### Task 2: Selective scene regeneration jobs

**Files:**
- Modify: `apps/orchestrator/src/app/services/image_pipeline.py`
- Modify: `apps/orchestrator/src/app/services/timeline.py`
- Modify: `apps/orchestrator/src/app/services/job_worker.py`
- Modify: `apps/orchestrator/src/app/http/dashboard_api.py`
- Create: `apps/orchestrator/tests/test_scene_regeneration.py`
- Modify: `apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 1: Write failing tests proving unchanged assets are reused**

```python
def test_regenerate_one_scene_does_not_call_other_scene_providers(self):
    result = service.regenerate("project_001", "scene_002", targets={"image"})
    self.image_provider.generate.assert_called_once()
    self.assertEqual(result["sceneId"], "scene_002")
    self.assertFalse(result["renderCurrent"])
```

- [ ] **Step 2: Run tests and verify operation is unavailable**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_scene_regeneration.py`

- [ ] **Step 3: Implement `regenerate_scene` job operation**

Add `POST /api/projects/{id}/scenes/{sceneId}/regenerate` with `targets` restricted to `image`, `audio`, or both. Validate the scene exists and no project job is active. Reuse provider validation and finite retry logic. Update manifest only after success and mark render stale.

- [ ] **Step 4: Run scene and API tests**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_scene_regeneration.py apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 5: Commit selective regeneration**

```powershell
git add apps/orchestrator/src/app/services/image_pipeline.py apps/orchestrator/src/app/services/timeline.py apps/orchestrator/src/app/services/job_worker.py apps/orchestrator/src/app/http/dashboard_api.py apps/orchestrator/tests/test_scene_regeneration.py apps/orchestrator/tests/test_dashboard_control_api.py
git commit -m "feat: regenerate selected scene assets"
```

### Task 3: Validated local media and download API

**Files:**
- Create: `apps/orchestrator/src/app/services/media_service.py`
- Modify: `apps/orchestrator/src/app/http/dashboard_api.py`
- Create: `apps/orchestrator/tests/test_media_service.py`
- Modify: `apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 1: Write failing containment and response tests**

```python
def test_media_rejects_traversal(self):
    with self.assertRaisesRegex(ValueError, "contained"):
        service.open_media("project_001", "../.env")

def test_mp4_download_sets_attachment(self):
    response = self.request("GET", "/api/projects/project_001/download")
    self.assertEqual(response.headers["Content-Type"], "video/mp4")
    self.assertIn("attachment", response.headers["Content-Disposition"])
```

- [ ] **Step 2: Run tests and verify missing media service/endpoints**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_media_service.py apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 3: Implement allowlisted media serving**

Resolve paths under the project directory and allow only manifest-referenced `.jpg`, `.wav`, and `.mp4` files. Verify file signatures, MIME, size bounds, and regular-file status before opening. Add `GET /api/projects/{id}/media?path=...` with inline disposition and `GET /api/projects/{id}/download` with attachment disposition. Stream fixed chunks; never load an MP4 fully into memory; support a single HTTP byte range for browser video seeking.

- [ ] **Step 4: Run media and API tests**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_media_service.py apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 5: Commit media API**

```powershell
git add apps/orchestrator/src/app/services/media_service.py apps/orchestrator/src/app/http/dashboard_api.py apps/orchestrator/tests/test_media_service.py apps/orchestrator/tests/test_dashboard_control_api.py
git commit -m "feat: serve validated project media"
```

### Task 4: Render and final-review jobs

**Files:**
- Modify: `apps/orchestrator/src/app/services/job_worker.py`
- Modify: `apps/orchestrator/src/app/services/dashboard_control.py`
- Modify: `apps/orchestrator/src/app/http/dashboard_api.py`
- Modify: `apps/orchestrator/tests/test_job_worker.py`
- Modify: `apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 1: Write failing render precondition and final decision tests**

```python
def test_render_rejects_stale_scene_assets(self):
    response = self.request("POST", "/api/projects/project_001/render")
    self.assertEqual(response.status, 409)
    self.assertEqual(response.json["code"], "stale_assets")

def test_final_change_request_accepts_notes(self):
    response = self.request("POST", "/api/projects/project_001/approve-final", {"approved": False, "reviewer": "human", "notes": "replace scene 2"})
    self.assertEqual(response.status, 200)
```

- [ ] **Step 2: Run tests and verify missing render contract**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_job_worker.py apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 3: Add render operation and final-review metadata**

`POST /api/projects/{id}/render` enqueues a render only when script approval is current and all required scene assets validate. Rendering writes a temporary MP4, validates it with ffprobe, atomically publishes it, records its hash in the manifest, and exposes `renderCurrent: true`. Final approval and change requests store bounded notes and current render hash so an approval cannot silently apply to a later render.

- [ ] **Step 4: Run worker, rendering, and API tests**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_job_worker.py apps/orchestrator/tests/test_rendering.py apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 5: Commit render control**

```powershell
git add apps/orchestrator/src/app/services/job_worker.py apps/orchestrator/src/app/services/dashboard_control.py apps/orchestrator/src/app/http/dashboard_api.py apps/orchestrator/tests/test_job_worker.py apps/orchestrator/tests/test_dashboard_control_api.py
git commit -m "feat: control final renders from web"
```

### Task 5: Final review and selective retry UI

**Files:**
- Create: `apps/dashboard/src/data/mediaRequests.js`
- Create: `apps/dashboard/src/components/FinalReview.jsx`
- Modify: `apps/dashboard/src/components/ProductionMonitor.jsx`
- Modify: `apps/dashboard/src/App.jsx`
- Modify: `apps/dashboard/src/styles.css`
- Create: `apps/dashboard/tests/mediaRequests.test.mjs`
- Modify: `apps/dashboard/tests/appStatic.test.mjs`

- [ ] **Step 1: Write failing request and static UI tests**

```javascript
test("download URL encodes only the project id", () => {
  assert.equal(projectDownloadUrl("project_001"), "/api/projects/project_001/download");
  assert.throws(() => projectDownloadUrl("../secret"), /project id/);
});
```

Assert the final view contains a `<video controls>` source from the API, download link, render/re-render action, approval/change request controls, and per-scene image/audio regeneration controls.

- [ ] **Step 2: Run dashboard tests and verify missing UI**

Run: `npm.cmd run test:dashboard`

- [ ] **Step 3: Implement final review**

Show whether the render is current, active render progress, video preview, quality issues, final notes, Approve, Request changes, Render again, and Download MP4. Disable final approval when the render hash is stale. Scene retry buttons send explicit target arrays and show the resulting background job in the existing monitor.

- [ ] **Step 4: Run dashboard tests and build**

Run: `npm.cmd run test:dashboard`

Run: `npm.cmd run build:dashboard`

- [ ] **Step 5: Commit final-review UI**

```powershell
git add apps/dashboard/src apps/dashboard/tests
git commit -m "feat: add browser final review and download"
```

### Task 6: Browser-to-MP4 acceptance and completion

**Files:**
- Create: `apps/orchestrator/tests/test_web_to_mp4_acceptance.py`
- Modify: `scripts/start-dashboard.ps1`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `goals/web-control-plane.md`

- [ ] **Step 1: Add local-provider web-to-MP4 acceptance**

Drive API contracts exactly as the browser does: save local-provider settings, create project, enqueue and poll script generation, approve current revision, enqueue and poll media production, render, fetch a byte range from the video endpoint, download the MP4, and assert the file begins with a valid MP4 `ftyp` box.

- [ ] **Step 2: Run the acceptance test**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_web_to_mp4_acceptance.py`

Expected: pass and create outputs only under the test temporary directory.

- [ ] **Step 3: Run full verification**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest discover apps/orchestrator/tests`

Run: `npm.cmd run test:renderer`

Run: `npm.cmd run test:dashboard`

Run: `npm.cmd run build:dashboard`

Expected: all pass without external provider traffic.

- [ ] **Step 4: Perform manual launcher acceptance**

Double-click `Start YouTube Studio.bat`, use the browser to create a local-provider project, complete both approval gates, play the video, and download it. Record service ports, output path, duration, and any limitation in `goals/web-control-plane.md` without recording secrets.

- [ ] **Step 5: Update operational documentation and commit completion evidence**

Document the browser-first workflow, backup/recovery paths, logs, launcher errors, and the deliberate YouTube-upload exclusion. Update `AGENTS.md` with new commands and test requirements.

```powershell
git add apps/orchestrator/tests/test_web_to_mp4_acceptance.py scripts/start-dashboard.ps1 README.md AGENTS.md goals/web-control-plane.md
git commit -m "test: verify complete browser video workflow"
```
