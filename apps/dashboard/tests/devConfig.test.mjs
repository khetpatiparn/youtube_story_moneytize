import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

test("dashboard dev config proxies api requests to the local control server", async () => {
  const viteConfigSource = await readFile("apps/dashboard/vite.config.mjs", "utf8");

  assert.match(viteConfigSource, /root:\s*dashboardRoot/);
  assert.match(viteConfigSource, /proxy:\s*\{/);
  assert.match(viteConfigSource, /"\/api":\s*"http:\/\/127\.0\.0\.1:8000"/);
});

test("package scripts use the dashboard vite config for dev and build", async () => {
  const packageJson = JSON.parse(await readFile("package.json", "utf8"));

  assert.match(packageJson.scripts["dev:dashboard"], /vite/);
  assert.match(packageJson.scripts["dev:dashboard"], /apps\/dashboard\/vite\.config\.mjs/);
  assert.doesNotMatch(packageJson.scripts["dev:dashboard"], /vite apps\/dashboard/);
  assert.match(packageJson.scripts["build:dashboard"], /apps\/dashboard\/vite\.config\.mjs/);
});

test("env example includes checkpoint db guidance for dashboard controls", async () => {
  const envExampleSource = await readFile(".env.example", "utf8");

  assert.match(envExampleSource, /CHECKPOINT_DB=/);
  assert.match(envExampleSource, /dashboard/i);
});
