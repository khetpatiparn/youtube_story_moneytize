import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

test("dashboard app exposes the media qa workspace sections", async () => {
  const appSource = await readFile("apps/dashboard/src/App.jsx", "utf8");
  const queueSource = await readFile("apps/dashboard/src/components/ProjectQueuePanel.jsx", "utf8");
  const scriptWorkspaceSource = await readFile("apps/dashboard/src/components/ScriptWorkspaceDrawer.jsx", "utf8");
  const surfaceSource = `${appSource}\n${queueSource}\n${scriptWorkspaceSource}`;

  assert.match(surfaceSource, /Media QA/);
  assert.match(surfaceSource, /Project Queue/);
  assert.match(appSource, /ProjectCreateForm/);
  assert.match(appSource, /SettingsPanel/);
  assert.match(surfaceSource, /ScriptReview/);
  assert.match(appSource, /ProductionMonitor/);
  assert.match(appSource, /EmptyProjectsState/);
  assert.match(appSource, /QueryClientProvider/);
  assert.match(appSource, /useQuery/);
  assert.match(appSource, /useMutation/);
  assert.match(appSource, /loadJobs/);
  assert.match(appSource, /loadProjectScript/);
  assert.match(appSource, /saveProjectScript/);
  assert.match(appSource, /approveScriptRevision/);
  assert.match(appSource, /runProjectJob/);
  assert.match(appSource, /Quality Report/);
  assert.match(appSource, /Approval Summary/);
  assert.match(appSource, /Control Panel/);
  assert.match(appSource, /@tanstack\/react-query/);
  assert.doesNotMatch(appSource, /return\s+\{projects:\s+\[sampleProject\],\s+mode:\s+"demo"\}/);
  assert.doesNotMatch(appSource, /localStorage/);
});

test("dashboard app is organized around shell, queue panel, and control rail", async () => {
  const appSource = await readFile("apps/dashboard/src/App.jsx", "utf8");

  assert.match(appSource, /DashboardShell/);
  assert.match(appSource, /ProjectQueuePanel/);
  assert.match(appSource, /ControlRail/);
});

test("dashboard app references LiveProductionPanel and loadProjectEvents", async () => {
  const appSource = await readFile("apps/dashboard/src/App.jsx", "utf8");

  assert.match(appSource, /LiveProductionPanel/);
  assert.match(appSource, /loadProjectEvents/);
});

test("dashboard app uses a secondary script workspace with active-job cancellation", async () => {
  const appSource = await readFile("apps/dashboard/src/App.jsx", "utf8");

  assert.match(appSource, /ScriptWorkspaceDrawer/);
  assert.match(appSource, /cancelJob/);
});
