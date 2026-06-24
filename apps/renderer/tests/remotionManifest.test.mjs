import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";

test("package exposes renderer verification and remotion render commands", async () => {
  const packageJson = JSON.parse(
    await readFile(new URL("../../../package.json", import.meta.url), "utf8"),
  );

  assert.equal(packageJson.scripts["test:renderer"], "node --test apps/renderer/tests/*.test.mjs");
  assert.match(packageJson.scripts["render:sample"], /remotion render apps\/renderer\/src\/index\.tsx YouTubeStory/);
  assert.equal(packageJson.dependencies.remotion, "^4.0.0");
  assert.equal(packageJson.dependencies["@remotion/cli"], "^4.0.0");
});

test("remotion entry registers the YouTubeStory composition", async () => {
  const entry = await readFile(
    new URL("../src/index.tsx", import.meta.url),
    "utf8",
  );

  assert.match(entry, /registerRoot\(RemotionRoot\)/);
  assert.match(entry, /id="YouTubeStory"/);
  assert.match(entry, /durationInFrames={calculatedFrames}/);
  assert.match(entry, /defaultProps={renderPayload}/);
  assert.match(entry, /useCurrentFrame\(\)/);
  assert.match(entry, /getMotionStyle\(scene\.motion, frame,/);
});
