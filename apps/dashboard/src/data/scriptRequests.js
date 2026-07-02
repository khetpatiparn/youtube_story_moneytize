async function parseJson(response) {
  return response.json().catch(() => ({}));
}

export async function loadProjectScript(fetchImpl, projectId) {
  const response = await fetchImpl(`/api/projects/${projectId}/script`);
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `script request failed with ${response.status}`);
  }
  return payload;
}

export async function saveProjectScript(fetchImpl, projectId, revision, scenes) {
  const response = await fetchImpl(`/api/projects/${projectId}/script`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({revision, scenes}),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `script save failed with ${response.status}`);
  }
  return payload;
}

export async function approveScriptRevision(fetchImpl, projectId, revision, approved, reviewer = "human") {
  const response = await fetchImpl(`/api/projects/${projectId}/approve-script`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({approved, reviewer, revision}),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `script approval failed with ${response.status}`);
  }
  return payload;
}
