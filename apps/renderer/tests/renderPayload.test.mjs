import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";

import {
  calculateDurationInFrames,
  getSceneAtFrame,
  validateRenderPayload,
} from "../src/renderPayload.js";
import {getMotionStyle} from "../src/motions/index.js";

test("sample render payload matches the static renderer contract", async () => {
  const payload = JSON.parse(
    await readFile(new URL("../sample/render_payload.json", import.meta.url), "utf8"),
  );

  const validated = validateRenderPayload(payload);

  assert.equal(validated.width, 1920);
  assert.equal(validated.height, 1080);
  assert.equal(validated.fps, 30);
  assert.equal(calculateDurationInFrames(validated), 210);
  assert.equal(validated.scenes[0].sceneId, "scene_001");
  assert.equal(validated.scenes[0].motion, "slow_push");
});

test("scene lookup returns the active scene for a frame", async () => {
  const payload = validateRenderPayload(
    JSON.parse(
      await readFile(new URL("../sample/render_payload.json", import.meta.url), "utf8"),
    ),
  );

  assert.equal(getSceneAtFrame(payload, 0).sceneId, "scene_001");
  assert.equal(getSceneAtFrame(payload, 151).sceneId, "scene_002");
  assert.equal(getSceneAtFrame(payload, 999).sceneId, "scene_002");
});

test("motion styles are deterministic and frame bounded", () => {
  const start = getMotionStyle("slow_push", 0, 90, [0.5, 0.4]);
  const end = getMotionStyle("slow_push", 90, 90, [0.5, 0.4]);

  assert.match(start.transform, /scale\(1\.0000\)/);
  assert.match(end.transform, /scale\(1\.0800\)/);
  assert.equal(start.transformOrigin, "50% 40%");
  assert.equal(end.transformOrigin, "50% 40%");
});
