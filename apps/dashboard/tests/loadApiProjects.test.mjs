import assert from "node:assert/strict";
import test from "node:test";

import {loadDashboardProjectsFromApi} from "../src/data/loadApiProjects.js";

test("loads projects from the live api payload", async () => {
  const payload = await loadDashboardProjectsFromApi(async () => ({
    ok: true,
    async json() {
      return {
        projects: [
          {
            projectId: "project_001",
            source: "live",
            availableActions: ["resume", "approve_final"],
          },
        ],
      };
    },
  }));

  assert.equal(payload.projects[0].source, "live");
  assert.deepEqual(payload.projects[0].availableActions, ["resume", "approve_final"]);
  assert.equal(payload.mode, "api");
});

test("raises a readable error when the api responds with a failure status", async () => {
  await assert.rejects(
    () =>
      loadDashboardProjectsFromApi(async () => ({
        ok: false,
        status: 500,
      })),
    /dashboard api returned 500/,
  );
});

test("raises when the api json payload is malformed", async () => {
  await assert.rejects(
    () =>
      loadDashboardProjectsFromApi(async () => ({
        ok: true,
        async json() {
          throw new Error("bad json");
        },
      })),
    /bad json/,
  );
});

test("raises when the api request rejects", async () => {
  await assert.rejects(
    () => loadDashboardProjectsFromApi(async () => Promise.reject(new Error("network down"))),
    /network down/,
  );
});

test("normalizes a missing projects array to an empty list", async () => {
  const payload = await loadDashboardProjectsFromApi(async () => ({
    ok: true,
    async json() {
      return {generatedAt: "2026-07-01T00:00:00Z"};
    },
  }));

  assert.deepEqual(payload.projects, []);
  assert.equal(payload.mode, "api");
});

test("live api empty response stays empty instead of swapping to demo data", async () => {
  const payload = await loadDashboardProjectsFromApi(async () => ({
    ok: true,
    async json() {
      return {projects: []};
    },
  }));

  assert.deepEqual(payload, {projects: [], mode: "api"});
});
