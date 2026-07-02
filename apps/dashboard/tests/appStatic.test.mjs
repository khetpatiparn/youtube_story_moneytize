import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

test("dashboard app exposes the media qa workspace sections", async () => {
  const appSource = await readFile("apps/dashboard/src/App.jsx", "utf8");

  assert.match(appSource, /Media QA/);
  assert.match(appSource, /Project Queue/);
  assert.match(appSource, /ProjectCreateForm/);
  assert.match(appSource, /SettingsPanel/);
  assert.match(appSource, /ScriptReview/);
  assert.match(appSource, /ProductionMonitor/);
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
  assert.doesNotMatch(appSource, /localStorage/);
});
