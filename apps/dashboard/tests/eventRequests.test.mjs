import assert from "node:assert/strict";
import test from "node:test";

import {loadProjectEvents} from "../src/data/eventRequests.js";

test("loadProjectEvents reads the project event timeline", async () => {
  const fetchImpl = async (url) => {
    assert.equal(url, "/api/projects/project_001/events");
    return {
      ok: true,
      json: async () => ({events: [{eventId: "evt_001", message: "Image generation started"}]}),
    };
  };

  const result = await loadProjectEvents(fetchImpl, "project_001");

  assert.equal(result.events[0].eventId, "evt_001");
});
