import assert from "node:assert/strict";
import test from "node:test";

import {approveScriptRevision, loadProjectScript, saveProjectScript} from "../src/data/scriptRequests.js";

test("loadProjectScript reads the script contract by project id", async () => {
  const fetchImpl = async (url) => {
    assert.equal(url, "/api/projects/project_001/script");
    return {ok: true, json: async () => ({revision: "rev_001", scenes: []})};
  };

  const result = await loadProjectScript(fetchImpl, "project_001");
  assert.equal(result.revision, "rev_001");
});

test("saveProjectScript sends revision and edited scenes", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/projects/project_001/script");
    assert.equal(options.method, "PUT");
    assert.deepEqual(JSON.parse(options.body), {
      revision: "rev_001",
      scenes: [{sceneId: "scene_001", narration: "Updated", prompt: "Prompt"}],
    });
    return {ok: true, json: async () => ({revision: "rev_002", scenes: []})};
  };

  const result = await saveProjectScript(fetchImpl, "project_001", "rev_001", [
    {sceneId: "scene_001", narration: "Updated", prompt: "Prompt"},
  ]);
  assert.equal(result.revision, "rev_002");
});

test("approveScriptRevision includes the current revision in the approval body", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/projects/project_001/approve-script");
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), {
      approved: true,
      reviewer: "human",
      revision: "rev_001",
    });
    return {ok: true, action: "approve_script", json: async () => ({ok: true})};
  };

  const result = await approveScriptRevision(fetchImpl, "project_001", "rev_001", true);
  assert.deepEqual(result, {ok: true});
});
