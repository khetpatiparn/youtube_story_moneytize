import assert from "node:assert/strict";
import test from "node:test";

import {saveSettings, testProviderSettings} from "../src/data/settingsRequests.js";

test("saveSettings posts json and never returns plaintext secrets", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/settings");
    assert.equal(options.method, "PUT");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), {gemini_api_key: "AQ.secret", story_provider: "gemini"});
    return {
      ok: true,
      json: async () => ({
        story_provider: "gemini",
        gemini_api_key: {configured: true, suffix: "cret"},
      }),
    };
  };

  const result = await saveSettings(fetchImpl, {gemini_api_key: "AQ.secret", story_provider: "gemini"});

  assert.deepEqual(result.gemini_api_key, {configured: true, suffix: "cret"});
  assert.equal(JSON.stringify(result).includes("AQ.secret"), false);
});

test("testProviderSettings posts only to explicit provider test endpoint", async () => {
  const fetchImpl = async (url, options) => {
    assert.equal(url, "/api/settings/test");
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), {provider: "gemini"});
    return {ok: true, json: async () => ({ok: true, provider: "gemini"})};
  };

  const result = await testProviderSettings(fetchImpl, "gemini");
  assert.deepEqual(result, {ok: true, provider: "gemini"});
});
