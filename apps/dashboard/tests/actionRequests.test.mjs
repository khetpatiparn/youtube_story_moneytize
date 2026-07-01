import assert from "node:assert/strict";
import test from "node:test";

import {submitProjectAction} from "../src/data/actionRequests.js";

test("posts run actions without a request body", async () => {
  const calls = [];
  const result = await submitProjectAction(
    async (url, options) => {
      calls.push({url, options});
      return {
        ok: true,
        async json() {
          return {ok: true, action: "run"};
        },
      };
    },
    "project_001",
    "run",
  );

  assert.equal(result.action, "run");
  assert.equal(calls[0].url, "/api/projects/project_001/run");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.body, undefined);
});

test("posts approval actions with a json body", async () => {
  const calls = [];
  await submitProjectAction(
    async (url, options) => {
      calls.push({url, options});
      return {
        ok: true,
        async json() {
          return {ok: true, action: "approve_script"};
        },
      };
    },
    "project_001",
    "approve-script",
    {approved: true, reviewer: "human"},
  );

  assert.equal(calls[0].url, "/api/projects/project_001/approve-script");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.equal(calls[0].options.body, JSON.stringify({approved: true, reviewer: "human"}));
});

test("supports change-request approvals", async () => {
  const calls = [];
  await submitProjectAction(
    async (url, options) => {
      calls.push({url, options});
      return {
        ok: true,
        async json() {
          return {ok: true, action: "approve_final"};
        },
      };
    },
    "project_001",
    "approve-final",
    {approved: false, reviewer: "human"},
  );

  assert.equal(calls[0].url, "/api/projects/project_001/approve-final");
  assert.equal(calls[0].options.body, JSON.stringify({approved: false, reviewer: "human"}));
});

test("raises a readable error when an action response is not ok", async () => {
  await assert.rejects(
    () =>
      submitProjectAction(
        async () => ({
          ok: false,
          status: 409,
          async json() {
            return {error: "Action already running."};
          },
        }),
        "project_001",
        "resume",
      ),
    /Action already running/,
  );
});
