# Media QA Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local read-only Media QA dashboard that shows generated scenes, render/report metadata, approval state, and quality issues, with demo fallback when no `projects/` runtime data exists.

**Architecture:** Add a separate `apps/dashboard/` React/Vite app so dashboard review UI stays separate from the Remotion renderer. Use a Node data export step to read local `projects/` files into `apps/dashboard/public/dashboard-data.json`; the browser UI fetches that static JSON and never imports filesystem APIs.

**Tech Stack:** Node built-in test runner, React 19, Vite, TypeScript/TSX for UI, JavaScript data loader for easy Node test execution.

---

## File Structure

- Create `apps/dashboard/src/data/sampleProject.js`: bundled demo project used when no runtime projects exist.
- Create `apps/dashboard/src/data/loadProjects.js`: filesystem loader and normalization helpers.
- Create `apps/dashboard/scripts/exportDashboardData.mjs`: writes dashboard JSON for the browser.
- Create `apps/dashboard/public/.gitkeep`: keeps the dashboard public folder present.
- Create `apps/dashboard/src/App.jsx`: Media QA dashboard shell and presentational components.
- Create `apps/dashboard/src/main.jsx`: React entrypoint.
- Create `apps/dashboard/src/styles.css`: compact operational dashboard styles.
- Create `apps/dashboard/index.html`: Vite HTML entrypoint.
- Create `apps/dashboard/tests/loadProjects.test.mjs`: deterministic loader tests using temporary fixtures.
- Create `apps/dashboard/tests/appStatic.test.mjs`: static contract test for dashboard source.
- Modify `package.json`: add dashboard scripts and dependencies.
- Modify `README.md`: document dashboard commands and demo fallback behavior.
- Modify `AGENTS.md`: document dashboard path, commands, and limitations.

## Task 1: Dashboard Data Loader and Export

**Files:**
- Create: `apps/dashboard/src/data/sampleProject.js`
- Create: `apps/dashboard/src/data/loadProjects.js`
- Create: `apps/dashboard/scripts/exportDashboardData.mjs`
- Create: `apps/dashboard/public/.gitkeep`
- Test: `apps/dashboard/tests/loadProjects.test.mjs`
- Modify: `package.json`

- [ ] **Step 1: Write the failing loader tests**

Create `apps/dashboard/tests/loadProjects.test.mjs`:

```js
import assert from "node:assert/strict";
import {mkdtemp, mkdir, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import path from "node:path";
import test from "node:test";

import {loadDashboardProjects} from "../src/data/loadProjects.js";

test("falls back to demo project when projects directory is missing", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "dashboard-missing-"));
  const projects = await loadDashboardProjects(path.join(root, "projects"));

  assert.equal(projects.length, 1);
  assert.equal(projects[0].source, "demo");
  assert.equal(projects[0].projectId, "demo_project");
  assert.ok(projects[0].scenes.length >= 2);
});

test("loads live project metadata scenes approvals and quality report", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "dashboard-live-"));
  const projectDir = path.join(root, "projects", "project_001");
  await mkdir(path.join(projectDir, "scenes"), {recursive: true});
  await mkdir(path.join(projectDir, "reports"), {recursive: true});

  await writeFile(
    path.join(projectDir, "metadata.json"),
    JSON.stringify({
      project_id: "project_001",
      topic: "A river spirit teaches patience",
      status: "final_changes_requested",
      target_duration_seconds: 180,
      target_language: "th",
    }),
  );
  await writeFile(
    path.join(projectDir, "scenes", "scenes.json"),
    JSON.stringify([
      {scene_id: "scene_001", image_path: "images/scene_001.png", prompt: "River at dawn"},
      {sceneId: "scene_002", imagePath: "images/scene_002.png", prompt: "Village bridge"},
    ]),
  );
  await writeFile(
    path.join(projectDir, "reports", "approvals.json"),
    JSON.stringify({
      script: {approved: true},
      final: {approved: false},
    }),
  );
  await writeFile(
    path.join(projectDir, "reports", "quality_report.json"),
    JSON.stringify({
      quality_score: 0.82,
      issues: ["Audio peak is slightly high"],
      video_path: "render/story.mp4",
    }),
  );

  const projects = await loadDashboardProjects(path.join(root, "projects"));

  assert.equal(projects.length, 1);
  assert.equal(projects[0].source, "live");
  assert.equal(projects[0].projectId, "project_001");
  assert.equal(projects[0].topic, "A river spirit teaches patience");
  assert.equal(projects[0].approvals.script, "approved");
  assert.equal(projects[0].approvals.final, "changes_requested");
  assert.equal(projects[0].quality.score, 0.82);
  assert.deepEqual(projects[0].quality.issues, ["Audio peak is slightly high"]);
  assert.equal(projects[0].scenes[1].sceneId, "scene_002");
});

test("handles missing optional reports without throwing", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "dashboard-partial-"));
  const projectDir = path.join(root, "projects", "project_002");
  await mkdir(projectDir, {recursive: true});
  await writeFile(
    path.join(projectDir, "metadata.json"),
    JSON.stringify({
      project_id: "project_002",
      topic: "A patient farmer",
      status: "created",
      target_duration_seconds: 120,
      target_language: "th",
    }),
  );

  const projects = await loadDashboardProjects(path.join(root, "projects"));

  assert.equal(projects[0].approvals.script, "pending");
  assert.equal(projects[0].approvals.final, "pending");
  assert.equal(projects[0].quality.score, null);
  assert.deepEqual(projects[0].quality.issues, []);
  assert.deepEqual(projects[0].scenes, []);
});
```

- [ ] **Step 2: Add the test script and verify RED**

Modify `package.json` scripts:

```json
"test:dashboard": "node --test apps/dashboard/tests/*.test.mjs"
```

Run:

```powershell
npm.cmd run test:dashboard
```

Expected: FAIL with module-not-found for `apps/dashboard/src/data/loadProjects.js`.

- [ ] **Step 3: Add demo project data**

Create `apps/dashboard/src/data/sampleProject.js`:

```js
export const sampleProject = {
  projectId: "demo_project",
  topic: "A river spirit teaches patience",
  status: "demo_media_ready",
  targetDurationSeconds: 180,
  targetLanguage: "th",
  source: "demo",
  scenes: [
    {
      sceneId: "scene_001",
      imagePath: "images/scene_001.svg",
      prompt: "A quiet river at sunrise with a small village in the distance",
    },
    {
      sceneId: "scene_002",
      imagePath: "images/scene_002.svg",
      prompt: "A patient elder teaching children near a wooden bridge",
    },
  ],
  approvals: {
    script: "approved",
    final: "changes_requested",
  },
  quality: {
    score: 0.82,
    issues: ["Audio peak is slightly high", "Scene 002 needs a brighter focal point"],
    videoPath: "render/story.mp4",
  },
  reports: {
    contactSheetPath: "reports/contact_sheet.md",
    projectReportPath: "reports/project_report.md",
    qualityReportPath: "reports/quality_report.json",
  },
};
```

- [ ] **Step 4: Implement the loader**

Create `apps/dashboard/src/data/loadProjects.js`:

```js
import {access, readdir, readFile} from "node:fs/promises";
import path from "node:path";

import {sampleProject} from "./sampleProject.js";

export async function loadDashboardProjects(projectsDir = path.resolve("projects")) {
  if (!(await exists(projectsDir))) {
    return [{...sampleProject}];
  }

  const entries = await readdir(projectsDir, {withFileTypes: true});
  const projectDirs = entries.filter((entry) => entry.isDirectory());
  if (projectDirs.length === 0) {
    return [{...sampleProject}];
  }

  const projects = [];
  for (const entry of projectDirs) {
    const project = await loadProject(path.join(projectsDir, entry.name));
    if (project) {
      projects.push(project);
    }
  }

  return projects.length > 0 ? projects : [{...sampleProject}];
}

async function loadProject(projectDir) {
  const metadata = await readJson(path.join(projectDir, "metadata.json"), null);
  if (!metadata) {
    return null;
  }

  const scenes = await readJson(path.join(projectDir, "scenes", "scenes.json"), []);
  const approvals = await readJson(path.join(projectDir, "reports", "approvals.json"), {});
  const quality = await readJson(path.join(projectDir, "reports", "quality_report.json"), {});

  return {
    projectId: String(metadata.project_id ?? path.basename(projectDir)),
    topic: String(metadata.topic ?? "Untitled project"),
    status: String(metadata.status ?? "unknown"),
    targetDurationSeconds: Number(metadata.target_duration_seconds ?? 0),
    targetLanguage: String(metadata.target_language ?? "unknown"),
    source: "live",
    scenes: normalizeScenes(Array.isArray(scenes) ? scenes : []),
    approvals: {
      script: normalizeApproval(approvals.script),
      final: normalizeApproval(approvals.final),
    },
    quality: {
      score: typeof quality.quality_score === "number" ? quality.quality_score : null,
      issues: Array.isArray(quality.issues) ? quality.issues.map(String) : [],
      videoPath: quality.video_path ? String(quality.video_path) : null,
    },
    reports: {
      contactSheetPath: "reports/contact_sheet.md",
      projectReportPath: "reports/project_report.md",
      qualityReportPath: quality.quality_score === undefined ? null : "reports/quality_report.json",
    },
  };
}

function normalizeScenes(scenes) {
  return scenes.map((scene, index) => ({
    sceneId: String(scene.scene_id ?? scene.sceneId ?? `scene_${String(index + 1).padStart(3, "0")}`),
    imagePath: scene.image_path || scene.imagePath ? String(scene.image_path ?? scene.imagePath) : null,
    prompt: scene.prompt ? String(scene.prompt) : null,
  }));
}

function normalizeApproval(value) {
  if (!value || typeof value !== "object") {
    return "pending";
  }
  return value.approved === true ? "approved" : "changes_requested";
}

async function readJson(filePath, fallback) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") {
      return fallback;
    }
    throw error;
  }
}

async function exists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}
```

- [ ] **Step 5: Add the dashboard data export script**

Create `apps/dashboard/scripts/exportDashboardData.mjs`:

```js
import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";

import {loadDashboardProjects} from "../src/data/loadProjects.js";

const projectRoot = process.cwd();
const projectsDir = path.join(projectRoot, "projects");
const outputDir = path.join(projectRoot, "apps", "dashboard", "public");
const outputPath = path.join(outputDir, "dashboard-data.json");

const projects = await loadDashboardProjects(projectsDir);
await mkdir(outputDir, {recursive: true});
await writeFile(
  outputPath,
  JSON.stringify({generatedAt: new Date().toISOString(), projects}, null, 2) + "\n",
  "utf8",
);

console.log(`Wrote ${outputPath} with ${projects.length} project(s).`);
```

Create `apps/dashboard/public/.gitkeep` as an empty file.

- [ ] **Step 6: Add export script and verify GREEN**

Modify `package.json` scripts:

```json
"prepare:dashboard-data": "node apps/dashboard/scripts/exportDashboardData.mjs"
```

Run:

```powershell
npm.cmd run test:dashboard
npm.cmd run prepare:dashboard-data
```

Expected: tests PASS and `apps/dashboard/public/dashboard-data.json` is generated with demo data because `projects/` is absent.

- [ ] **Step 7: Verify generated dashboard data is ignored**

Add to `.gitignore` if missing:

```gitignore
apps/dashboard/public/dashboard-data.json
```

Run:

```powershell
git check-ignore -v apps/dashboard/public/dashboard-data.json
```

Expected: `.gitignore` matches the generated JSON file.

- [ ] **Step 8: Commit**

```powershell
git add .gitignore package.json apps/dashboard/src/data apps/dashboard/scripts apps/dashboard/public/.gitkeep apps/dashboard/tests/loadProjects.test.mjs
git commit -m "feat: add dashboard project loader"
```

## Task 2: Dashboard UI Shell

**Files:**
- Create: `apps/dashboard/src/App.jsx`
- Create: `apps/dashboard/src/main.jsx`
- Create: `apps/dashboard/src/styles.css`
- Create: `apps/dashboard/index.html`
- Test: `apps/dashboard/tests/appStatic.test.mjs`
- Modify: `package.json`

- [ ] **Step 1: Write the failing static UI contract test**

Create `apps/dashboard/tests/appStatic.test.mjs`:

```js
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

test("dashboard app exposes the media qa workspace sections", async () => {
  const appSource = await readFile("apps/dashboard/src/App.jsx", "utf8");

  assert.match(appSource, /Media QA/);
  assert.match(appSource, /Project Queue/);
  assert.match(appSource, /Scene Review/);
  assert.match(appSource, /Quality Report/);
  assert.match(appSource, /Approval Summary/);
});
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
npm.cmd run test:dashboard
```

Expected: FAIL because `apps/dashboard/src/App.jsx` does not exist.

- [ ] **Step 3: Add dashboard scripts and Vite dependency declarations**

Modify `package.json`:

```json
"dev:dashboard": "npm run prepare:dashboard-data && vite apps/dashboard --host 127.0.0.1",
"build:dashboard": "npm run prepare:dashboard-data && vite build apps/dashboard --outDir ../../dist/dashboard"
```

Add dev dependency:

```json
"vite": "^5.0.0"
```

- [ ] **Step 4: Create the Vite entrypoint**

Create `apps/dashboard/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>YouTube Story Media QA</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

Create `apps/dashboard/src/main.jsx`:

```jsx
import React from "react";
import {createRoot} from "react-dom/client";

import {App} from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 5: Implement the Media QA dashboard UI**

Create `apps/dashboard/src/App.jsx`:

```jsx
import React, {useEffect, useState} from "react";

import {sampleProject} from "./data/sampleProject.js";

const statusLabels = {
  approved: "Approved",
  changes_requested: "Changes requested",
  pending: "Pending",
};

export function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/dashboard-data.json")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`dashboard data returned ${response.status}`);
        }
        return response.json();
      })
      .then((payload) => {
        const loadedProjects = Array.isArray(payload.projects) ? payload.projects : [sampleProject];
        setProjects(loadedProjects);
        setSelectedProjectId(loadedProjects[0]?.projectId ?? null);
      })
      .catch(() => {
        setProjects([sampleProject]);
        setSelectedProjectId(sampleProject.projectId);
      });
  }, []);

  const selectedProject = projects.find((project) => project.projectId === selectedProjectId) ?? projects[0];

  if (error) {
    return <main className="app-shell error-state">Dashboard failed to load: {error}</main>;
  }

  if (!selectedProject) {
    return <main className="app-shell empty-state">No project data available.</main>;
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span>Media QA</span>
          <strong>YouTube Story Automation</strong>
        </div>
        <section>
          <h2>Project Queue</h2>
          {projects.map((project) => (
            <button
              className={project.projectId === selectedProject.projectId ? "project-item active" : "project-item"}
              key={project.projectId}
              onClick={() => setSelectedProjectId(project.projectId)}
              type="button"
            >
              <span>{project.projectId}</span>
              <small>{project.status}</small>
            </button>
          ))}
        </section>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">{selectedProject.source === "demo" ? "Demo data" : "Live project"}</p>
            <h1>{selectedProject.topic}</h1>
            <p>
              {selectedProject.projectId} / {selectedProject.targetDurationSeconds}s / {selectedProject.targetLanguage}
            </p>
          </div>
          <div className="score-box">
            <span>Quality score</span>
            <strong>{selectedProject.quality.score === null ? "N/A" : selectedProject.quality.score.toFixed(2)}</strong>
          </div>
        </header>

        <div className="content-grid">
          <section className="panel scene-panel">
            <h2>Scene Review</h2>
            <div className="scene-grid">
              {selectedProject.scenes.map((scene) => (
                <article className="scene-card" key={scene.sceneId}>
                  <div className="scene-thumb">{scene.imagePath ?? "No image"}</div>
                  <h3>{scene.sceneId}</h3>
                  <p>{scene.prompt ?? "No prompt available"}</p>
                </article>
              ))}
              {selectedProject.scenes.length === 0 ? <p className="muted">No scenes are available yet.</p> : null}
            </div>
          </section>

          <aside className="right-rail">
            <section className="panel">
              <h2>Quality Report</h2>
              <p className="video-path">{selectedProject.quality.videoPath ?? "No render path yet"}</p>
              <ul className="issue-list">
                {selectedProject.quality.issues.length === 0 ? (
                  <li>No quality issues recorded.</li>
                ) : (
                  selectedProject.quality.issues.map((issue) => <li key={issue}>{issue}</li>)
                )}
              </ul>
            </section>

            <section className="panel">
              <h2>Approval Summary</h2>
              <ApprovalRow label="Script" value={selectedProject.approvals.script} />
              <ApprovalRow label="Final" value={selectedProject.approvals.final} />
            </section>

            <section className="panel">
              <h2>Reports</h2>
              <ReportPath label="Contact sheet" value={selectedProject.reports.contactSheetPath} />
              <ReportPath label="Project report" value={selectedProject.reports.projectReportPath} />
              <ReportPath label="Quality JSON" value={selectedProject.reports.qualityReportPath} />
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
}

function ApprovalRow({label, value}) {
  return (
    <div className="approval-row">
      <span>{label}</span>
      <strong>{statusLabels[value]}</strong>
    </div>
  );
}

function ReportPath({label, value}) {
  return (
    <div className="report-path">
      <span>{label}</span>
      <code>{value ?? "Unavailable"}</code>
    </div>
  );
}
```

- [ ] **Step 6: Add compact dashboard styles**

Create `apps/dashboard/src/styles.css`:

```css
:root {
  color: #172026;
  background: #eef2f5;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}

button {
  font: inherit;
}

.app-shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  min-height: 100vh;
  background: #eef2f5;
}

.sidebar {
  background: #172026;
  color: #f8fafc;
  padding: 24px;
}

.brand {
  display: grid;
  gap: 6px;
  margin-bottom: 28px;
}

.brand span,
.eyebrow {
  color: #5eead4;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.brand strong {
  font-size: 18px;
  line-height: 1.25;
}

h1,
h2,
h3,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 8px;
  font-size: 28px;
}

h2 {
  font-size: 15px;
}

.project-item {
  width: 100%;
  display: grid;
  gap: 4px;
  margin-bottom: 10px;
  padding: 12px;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #22313a;
  color: #f8fafc;
  text-align: left;
  cursor: pointer;
}

.project-item.active {
  border-color: #5eead4;
  background: #2f4a4d;
}

.project-item small {
  color: #cbd5e1;
}

.workspace {
  padding: 24px;
}

.workspace-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.score-box,
.panel {
  border: 1px solid #d1d9e0;
  border-radius: 8px;
  background: #ffffff;
}

.score-box {
  min-width: 170px;
  padding: 16px;
}

.score-box span {
  display: block;
  color: #64748b;
  font-size: 13px;
}

.score-box strong {
  font-size: 34px;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
}

.panel {
  padding: 16px;
}

.scene-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.scene-card {
  border: 1px solid #dbe3ea;
  border-radius: 8px;
  padding: 12px;
  background: #f8fafc;
}

.scene-thumb {
  min-height: 116px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
  border-radius: 6px;
  background: #d9e6ed;
  color: #334155;
  overflow-wrap: anywhere;
  text-align: center;
}

.scene-card h3 {
  font-size: 15px;
}

.scene-card p,
.muted,
.video-path,
.issue-list,
.report-path {
  color: #475569;
  font-size: 14px;
}

.right-rail {
  display: grid;
  gap: 14px;
  align-content: start;
}

.issue-list {
  padding-left: 18px;
}

.approval-row,
.report-path {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-top: 1px solid #e2e8f0;
}

.report-path code {
  max-width: 155px;
  overflow-wrap: anywhere;
}

.error-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

@media (max-width: 900px) {
  .app-shell,
  .content-grid {
    grid-template-columns: 1fr;
  }

  .workspace-header {
    flex-direction: column;
  }
}
```

- [ ] **Step 7: Verify GREEN**

Run:

```powershell
npm.cmd run test:dashboard
```

Expected: PASS for loader tests and static UI contract test.

- [ ] **Step 8: Install dependency if needed and build**

If `vite` is not installed yet, run:

```powershell
npm.cmd install
```

Then run:

```powershell
npm.cmd run prepare:dashboard-data
npm.cmd run build:dashboard
```

Expected: Vite build completes and writes `dist/dashboard`.

- [ ] **Step 9: Commit**

```powershell
git add package.json package-lock.json apps/dashboard
git commit -m "feat: add media qa dashboard shell"
```

## Task 3: Documentation and Repo Guidance

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write a failing documentation check**

Run:

```powershell
Select-String -Path README.md,AGENTS.md -Pattern "dev:dashboard|test:dashboard|apps/dashboard"
```

Expected: missing one or more dashboard references.

- [ ] **Step 2: Update README commands**

Add a dashboard section to `README.md`:

```md
## Current Dashboard Commands

```powershell
npm.cmd run test:dashboard
npm.cmd run dev:dashboard
npm.cmd run prepare:dashboard-data
npm.cmd run build:dashboard
```

The Media QA dashboard lives in `apps/dashboard/`. Run `npm.cmd run prepare:dashboard-data` before opening or building it. That export step reads local project data from `projects/{project_id}/` when available and writes `apps/dashboard/public/dashboard-data.json`; when no generated projects exist it writes bundled demo data.
```

- [ ] **Step 3: Update AGENTS guidance**

Update `AGENTS.md`:

```md
- `apps/dashboard/` for the local Media QA web dashboard.
```

Add command bullets:

```md
- `npm.cmd run test:dashboard` validates dashboard data loading and UI contracts.
- `npm.cmd run prepare:dashboard-data` exports local project/report data for the browser dashboard.
- `npm.cmd run dev:dashboard` starts the local Media QA dashboard.
- `npm.cmd run build:dashboard` builds the dashboard static bundle.
```

Add limitation:

```md
The dashboard is read-only in the first slice; do not add pipeline execution, approval writes, or upload actions without a new goal and tests.
```

- [ ] **Step 4: Verify documentation**

Run:

```powershell
Select-String -Path README.md,AGENTS.md -Pattern "dev:dashboard|test:dashboard|apps/dashboard"
```

Expected: both docs contain dashboard paths and commands.

- [ ] **Step 5: Commit**

```powershell
git add README.md AGENTS.md
git commit -m "docs: document media qa dashboard"
```

## Task 4: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run dashboard tests**

```powershell
npm.cmd run test:dashboard
```

Expected: PASS.

- [ ] **Step 2: Run renderer tests**

```powershell
npm.cmd run test:renderer
```

Expected: PASS.

- [ ] **Step 3: Run orchestrator tests**

```powershell
$env:PYTHONPATH='apps/orchestrator/src'
python -m unittest discover apps/orchestrator/tests
```

Expected: PASS.

- [ ] **Step 4: Run dashboard build**

```powershell
npm.cmd run build:dashboard
```

Expected: PASS.

- [ ] **Step 5: Check whitespace and worktree**

```powershell
git diff --check
git status --short --branch
```

Expected: no whitespace errors, branch contains only intended committed changes or a clean worktree.

- [ ] **Step 6: Final review note**

Summarize:

- New dashboard app path.
- Whether live and demo data modes are covered by tests.
- Verification commands and results.
- Remaining limitation: no browser write actions in this slice.
