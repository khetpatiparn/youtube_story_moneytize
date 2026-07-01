# Web Control Plane Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Windows user double-click one file, open the local dashboard, configure encrypted provider credentials, and create a real project without using a terminal.

**Architecture:** Keep the existing Python pipeline and `http.server` API. Add a Windows DPAPI-backed settings service, project-creation endpoints, dashboard screens, and a PowerShell launcher behind a `.bat` entrypoint. The CLI remains available for diagnostics.

**Tech Stack:** Python 3.11+, `ctypes` DPAPI, `http.server`, React 19, Vite 5, Node test runner, PowerShell.

---

### Task 1: Encrypted local settings store

**Files:**
- Create: `apps/orchestrator/src/app/services/secret_store.py`
- Create: `apps/orchestrator/src/app/services/dashboard_settings.py`
- Test: `apps/orchestrator/tests/test_dashboard_settings.py`

- [ ] **Step 1: Write failing tests for masking, encryption boundaries, and non-secret settings**

```python
def test_settings_response_never_returns_plaintext_key(self):
    service = DashboardSettingsService(self.path, _ReversibleProtector())
    service.update({"gemini_api_key": "AQ.secret", "story_provider": "gemini"})
    self.assertEqual(service.public_settings()["gemini_api_key"], {"configured": True, "suffix": "cret"})
    self.assertNotIn("AQ.secret", self.path.read_text(encoding="utf-8"))

def test_remove_secret_clears_configured_state(self):
    service = DashboardSettingsService(self.path, _ReversibleProtector())
    service.update({"gemini_api_key": "AQ.secret"})
    service.update({"gemini_api_key": None})
    self.assertFalse(service.public_settings()["gemini_api_key"]["configured"])
```

- [ ] **Step 2: Run the new test and verify it fails because the modules do not exist**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_settings.py`

Expected: `ModuleNotFoundError` for `app.services.dashboard_settings`.

- [ ] **Step 3: Implement a protector boundary and JSON settings service**

```python
class SecretProtector(Protocol):
    def protect(self, value: str) -> str: ...
    def unprotect(self, value: str) -> str: ...

SECRET_FIELDS = {"gemini_api_key", "cloudflare_account_id", "cloudflare_api_token"}

class DashboardSettingsService:
    def update(self, changes: dict[str, object]) -> dict[str, object]:
        current = self._load_raw()
        for key, value in changes.items():
            if key in SECRET_FIELDS:
                if value is None:
                    current.pop(key, None)
                elif isinstance(value, str) and value.strip():
                    current[key] = self.protector.protect(value.strip())
                else:
                    raise ValueError(f"{key} must be a nonempty string or null")
            else:
                current[key] = value
        self._atomic_write(current)
        return self.public_settings()
```

Implement `WindowsDpapiProtector` with `CryptProtectData` and `CryptUnprotectData`, Base64 encoding only the encrypted bytes. Restrict provider values to `local`, `gemini`, and `cloudflare` as applicable; retry bounds to `1..5`; and projects directory to a nonempty local path.

- [ ] **Step 4: Run the settings tests and the complete Python suite**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_settings.py`

Expected: all settings tests pass and plaintext is absent from the settings file.

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest discover apps/orchestrator/tests`

Expected: existing suite passes without external requests.

- [ ] **Step 5: Commit the settings boundary**

```powershell
git add apps/orchestrator/src/app/services/secret_store.py apps/orchestrator/src/app/services/dashboard_settings.py apps/orchestrator/tests/test_dashboard_settings.py
git commit -m "feat: add encrypted dashboard settings"
```

### Task 2: Settings and health API

**Files:**
- Modify: `apps/orchestrator/src/app/http/dashboard_api.py`
- Modify: `apps/orchestrator/src/app/cli/main.py`
- Modify: `apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 1: Add failing API tests**

```python
def test_health_endpoint_reports_ready(self):
    response = self.request("GET", "/api/health")
    self.assertEqual(response.json, {"ok": True})

def test_put_settings_never_echoes_secret(self):
    response = self.request("PUT", "/api/settings", {"gemini_api_key": "AQ.secret"})
    self.assertEqual(response.status, 200)
    self.assertNotIn("AQ.secret", response.body.decode())

def test_provider_test_is_never_triggered_by_get_or_put(self):
    self.request("GET", "/api/settings")
    self.request("PUT", "/api/settings", {"story_provider": "local"})
    self.settings_tester.test.assert_not_called()
```

- [ ] **Step 2: Run the focused API tests and verify 404/failure**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_control_api.py`

Expected: the new health and settings assertions fail.

- [ ] **Step 3: Route health and settings explicitly**

```python
if parts == ["api", "health"]:
    self._write_json(200, {"ok": True})
    return
if parts == ["api", "settings"]:
    self._write_json(200, self.server.settings_service.public_settings())
    return
```

Add `do_PUT` for `/api/settings`, enforce `Content-Type: application/json`, reject bodies above 64 KiB before reading, and call `settings_service.update(body)`. Add explicit `POST /api/settings/test` for one allowlisted provider and an injected settings tester. Reads, saves, page loads, and default tests must never trigger provider traffic. Inject both services from `_run_dashboard_api`; do not read secrets in the request handler.

- [ ] **Step 4: Run API tests**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_control_api.py`

Expected: all dashboard API tests pass.

- [ ] **Step 5: Commit the settings API**

```powershell
git add apps/orchestrator/src/app/http/dashboard_api.py apps/orchestrator/src/app/cli/main.py apps/orchestrator/tests/test_dashboard_control_api.py
git commit -m "feat: expose local dashboard settings api"
```

### Task 3: Project creation API

**Files:**
- Modify: `apps/orchestrator/src/app/services/dashboard_control.py`
- Modify: `apps/orchestrator/src/app/http/dashboard_api.py`
- Modify: `apps/orchestrator/tests/test_dashboard_control_service.py`
- Modify: `apps/orchestrator/tests/test_dashboard_control_api.py`

- [ ] **Step 1: Write failing service and endpoint tests**

```python
def test_create_project_returns_dashboard_summary(self):
    created = self._service().create_project({
        "topic": "River spirit", "duration": 60,
        "profile": "simple_story_th", "targetLanguage": "th",
    })
    self.assertEqual(created["status"], "created")
    self.assertEqual(created["availableActions"], ["run"])

def test_create_project_rejects_unknown_field(self):
    response = self.request("POST", "/api/projects", {"topic": "x", "duration": 60, "profile": "simple_story_th", "admin": True})
    self.assertEqual(response.status, 400)

def test_copy_then_delete_requires_exact_confirmation(self):
    copied = self.request("POST", "/api/projects/project_001/copy", {})
    denied = self.request("DELETE", f"/api/projects/{copied.json['projectId']}", {"confirmProjectId": "wrong"})
    self.assertEqual(copied.status, 201)
    self.assertEqual(denied.status, 400)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_control_service.py apps/orchestrator/tests/test_dashboard_control_api.py`

Expected: `create_project` and `POST /api/projects` are unavailable.

- [ ] **Step 3: Implement validated project creation**

```python
CREATE_FIELDS = {"topic", "duration", "profile", "targetLanguage", "projectId"}

def create_project(self, payload: dict[str, object]) -> dict[str, object]:
    unknown = set(payload) - CREATE_FIELDS
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    request = CreateProjectRequest(
        topic=payload.get("topic", ""),
        duration=payload.get("duration"),
        profile=payload.get("profile", ""),
        target_language=payload.get("targetLanguage", "th"),
    )
    metadata = self.projects.create_project(request, project_id=payload.get("projectId"))
    return build_project_summary(metadata, None, self.projects.project_dir(metadata.project_id))
```

Route `POST /api/projects` before project-action routing and return `201`. Limit topic to 500 characters, duration to `15..3600`, language to 16 characters, profile to 64 characters, and optional project ID through the repository's existing contained-path validation. Add `POST /api/projects/{id}/copy`, copying inputs and metadata but excluding credentials, checkpoints, and generated outputs. Add `DELETE /api/projects/{id}` only when no job is active and `confirmProjectId` exactly matches; rename into a repository-local trash directory before cleanup so interruption is recoverable.

- [ ] **Step 4: Run focused and full Python tests**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest discover apps/orchestrator/tests`

Expected: all tests pass with no provider network calls.

- [ ] **Step 5: Commit project creation**

```powershell
git add apps/orchestrator/src/app/services/dashboard_control.py apps/orchestrator/src/app/http/dashboard_api.py apps/orchestrator/tests/test_dashboard_control_service.py apps/orchestrator/tests/test_dashboard_control_api.py
git commit -m "feat: create projects from dashboard api"
```

### Task 4: Browser project creation and settings screens

**Files:**
- Create: `apps/dashboard/src/data/settingsRequests.js`
- Create: `apps/dashboard/src/data/projectRequests.js`
- Create: `apps/dashboard/src/components/ProjectCreateForm.jsx`
- Create: `apps/dashboard/src/components/SettingsPanel.jsx`
- Modify: `apps/dashboard/src/App.jsx`
- Modify: `apps/dashboard/src/styles.css`
- Create: `apps/dashboard/tests/settingsRequests.test.mjs`
- Create: `apps/dashboard/tests/projectRequests.test.mjs`
- Modify: `apps/dashboard/tests/appStatic.test.mjs`

- [ ] **Step 1: Write failing request-contract and static UI tests**

```javascript
test("createProject posts the exact creation contract", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/projects");
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), {topic: "River", duration: 60, profile: "simple_story_th", targetLanguage: "th"});
    return {ok: true, json: async () => ({projectId: "project_001"})};
  };
  assert.equal((await createProject(fetchImpl, {topic: "River", duration: 60, profile: "simple_story_th", targetLanguage: "th"})).projectId, "project_001");
});
```

Assert `App.jsx` imports and renders `ProjectCreateForm` and `SettingsPanel`, and that no password value is persisted to `localStorage`.

- [ ] **Step 2: Run dashboard tests and verify module/import failures**

Run: `npm.cmd run test:dashboard`

Expected: new request modules and components are missing.

- [ ] **Step 3: Implement request helpers and two dashboard views**

```javascript
export async function createProject(fetchImpl, input) {
  const response = await fetchImpl("/api/projects", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(input),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error ?? `project creation failed with ${response.status}`);
  return payload;
}
```

Use controlled inputs. Clear secret fields after successful save. Render only `{configured, suffix}` returned by the API. After creation, prepend the returned project and select it. Add Copy and Delete controls; deletion requires typing the exact project ID. Add an explicit Test button for each configured provider; saving or opening Settings never tests automatically. Disable submit while a request is active and show the sanitized API error inline.

- [ ] **Step 4: Run dashboard tests and build**

Run: `npm.cmd run test:dashboard`

Expected: all dashboard tests pass.

Run: `npm.cmd run build:dashboard`

Expected: Vite build succeeds.

- [ ] **Step 5: Commit the web forms**

```powershell
git add apps/dashboard/src apps/dashboard/tests
git commit -m "feat: add web project and settings forms"
```

### Task 5: One-click Windows launcher

**Files:**
- Create: `scripts/start-dashboard.ps1`
- Create: `Start YouTube Studio.bat`
- Create: `apps/orchestrator/tests/test_dashboard_launcher.py`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write a failing launcher contract test**

```python
def test_launcher_uses_loopback_and_health_check(self):
    script = Path("scripts/start-dashboard.ps1").read_text(encoding="utf-8-sig")
    self.assertIn("127.0.0.1", script)
    self.assertIn("/api/health", script)
    self.assertIn("Start-Process", script)
    self.assertNotIn("0.0.0.0", script)
```

- [ ] **Step 2: Run the launcher test and verify missing-file failure**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_launcher.py`

Expected: `FileNotFoundError` for `scripts/start-dashboard.ps1`.

- [ ] **Step 3: Implement launcher and wrapper**

```bat
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\start-dashboard.ps1"
```

The PowerShell script resolves the repository root, checks `.venv\Scripts\python.exe`, `node_modules`, and ports 8000/5173; starts `python -m app dashboard-api` and `npm.cmd run dev:dashboard -- --port 5173` with hidden windows and logs under `tmp/launcher/`; polls `http://127.0.0.1:8000/api/health` and `http://127.0.0.1:5173/` for at most 30 seconds; opens the dashboard; and shows a Windows message box containing the log path on failure.

- [ ] **Step 4: Run launcher, Python, dashboard, and build verification**

Run: `$env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_launcher.py`

Run: `npm.cmd run test:dashboard`

Run: `npm.cmd run build:dashboard`

Expected: all pass; manual double-click opens the dashboard without a persistent terminal window.

- [ ] **Step 5: Commit launcher and documentation**

```powershell
git add scripts/start-dashboard.ps1 'Start YouTube Studio.bat' apps/orchestrator/tests/test_dashboard_launcher.py .gitignore README.md AGENTS.md
git commit -m "feat: add one-click dashboard launcher"
```

### Task 6: Slice 1 acceptance

**Files:**
- Create: `apps/orchestrator/tests/test_dashboard_web_acceptance.py`
- Create: `goals/web-control-plane.md`

- [ ] **Step 1: Add an acceptance test using temporary projects, settings, and port zero**

```python
def test_settings_then_create_project_without_cli(self):
    settings = self.request("PUT", "/api/settings", {"story_provider": "local"})
    created = self.request("POST", "/api/projects", {"topic": "River", "duration": 30, "profile": "simple_story_th", "targetLanguage": "th"})
    listed = self.request("GET", "/api/projects")
    self.assertEqual(settings.status, 200)
    self.assertEqual(created.status, 201)
    self.assertEqual(listed.json["projects"][0]["projectId"], created.json["projectId"])
```

- [ ] **Step 2: Run the acceptance test and fix only contract mismatches found by it**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest apps/orchestrator/tests/test_dashboard_web_acceptance.py`

Expected: pass without an external request.

- [ ] **Step 3: Run all verification**

Run: `$env:IMAGE_PROVIDER='local'; $env:TTS_PROVIDER='local'; $env:PYTHONPATH='apps/orchestrator/src'; python -m unittest discover apps/orchestrator/tests`

Run: `npm.cmd run test:dashboard`

Run: `npm.cmd run build:dashboard`

Expected: all pass.

- [ ] **Step 4: Record acceptance evidence in the goal**

Add exact commands, pass counts, manual launcher result, known limitations, and the next plan path to `goals/web-control-plane.md`.

- [ ] **Step 5: Commit Slice 1 acceptance**

```powershell
git add apps/orchestrator/tests/test_dashboard_web_acceptance.py goals/web-control-plane.md
git commit -m "test: verify web setup and project creation"
```
