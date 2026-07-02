import assert from "node:assert/strict";
import test from "node:test";

import {cancelJob, loadJob, loadJobs, runProjectJob} from "../src/data/jobRequests.js";

test("runProjectJob posts to the run endpoint and returns accepted job", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/projects/project_001/run");
    assert.equal(options.method, "POST");
    return {
      ok: true,
      json: async () => ({job: {jobId: "job_001", status: "queued", operation: "run"}}),
    };
  };

  const result = await runProjectJob(fetchImpl, "project_001", "run");
  assert.equal(result.job.jobId, "job_001");
});

test("loadJobs filters by project id", async () => {
  const fetchImpl = async (url) => {
    assert.equal(url, "/api/jobs?projectId=project_001");
    return {
      ok: true,
      json: async () => ({jobs: [{jobId: "job_001", projectId: "project_001"}]}),
    };
  };

  const result = await loadJobs(fetchImpl, "project_001");
  assert.equal(result.jobs[0].jobId, "job_001");
});

test("loadJob reads one job by id", async () => {
  const fetchImpl = async (url) => {
    assert.equal(url, "/api/jobs/job_001");
    return {ok: true, json: async () => ({job: {jobId: "job_001", status: "running"}})};
  };

  const result = await loadJob(fetchImpl, "job_001");
  assert.equal(result.job.status, "running");
});

test("cancelJob posts to explicit cancel endpoint", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/jobs/job_001/cancel");
    assert.equal(options.method, "POST");
    return {ok: true, json: async () => ({job: {jobId: "job_001", status: "cancelling"}})};
  };

  const result = await cancelJob(fetchImpl, "job_001");
  assert.equal(result.job.status, "cancelling");
});
