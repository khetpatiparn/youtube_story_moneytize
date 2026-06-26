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

test("falls back to demo project when metadata is malformed", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "dashboard-invalid-metadata-"));
  const projectDir = path.join(root, "projects", "project_003");
  await mkdir(projectDir, {recursive: true});
  await writeFile(path.join(projectDir, "metadata.json"), "{");

  const projects = await loadDashboardProjects(path.join(root, "projects"));

  assert.equal(projects.length, 1);
  assert.equal(projects[0].source, "demo");
  assert.equal(projects[0].projectId, "demo_project");
});
