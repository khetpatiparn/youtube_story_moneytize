import assert from "node:assert/strict";
import test from "node:test";

import {copyProject, createProject, deleteProject} from "../src/data/projectRequests.js";

test("createProject posts the exact creation contract", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/projects");
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), {
      topic: "River",
      duration: 60,
      profile: "simple_story_th",
      targetLanguage: "th",
    });
    return {ok: true, json: async () => ({projectId: "project_001"})};
  };

  const result = await createProject(fetchImpl, {
    topic: "River",
    duration: 60,
    profile: "simple_story_th",
    targetLanguage: "th",
  });
  assert.equal(result.projectId, "project_001");
});

test("copyProject uses the explicit copy endpoint", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/projects/project_001/copy");
    assert.equal(options.method, "POST");
    return {ok: true, json: async () => ({projectId: "project_002"})};
  };

  const result = await copyProject(fetchImpl, "project_001");
  assert.equal(result.projectId, "project_002");
});

test("deleteProject requires exact confirmation payload", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/projects/project_001");
    assert.equal(options.method, "DELETE");
    assert.deepEqual(JSON.parse(options.body), {confirmProjectId: "project_001"});
    return {ok: true, json: async () => ({ok: true, projectId: "project_001"})};
  };

  const result = await deleteProject(fetchImpl, "project_001", "project_001");
  assert.deepEqual(result, {ok: true, projectId: "project_001"});
});
