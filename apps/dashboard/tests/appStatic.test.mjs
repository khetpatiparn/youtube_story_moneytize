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
  assert.match(appSource, /Control Panel/);
  assert.match(appSource, /Approve script/);
  assert.match(appSource, /Request script changes/);
  assert.match(appSource, /Approve final/);
});
