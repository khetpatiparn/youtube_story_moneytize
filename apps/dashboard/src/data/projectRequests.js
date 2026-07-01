async function parseJson(response) {
  return response.json().catch(() => ({}));
}

export async function createProject(fetchImpl, input) {
  const response = await fetchImpl("/api/projects", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(input),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `project creation failed with ${response.status}`);
  }
  return payload;
}

export async function copyProject(fetchImpl, projectId) {
  const response = await fetchImpl(`/api/projects/${projectId}/copy`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({}),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `project copy failed with ${response.status}`);
  }
  return payload;
}

export async function deleteProject(fetchImpl, projectId, confirmProjectId) {
  const response = await fetchImpl(`/api/projects/${projectId}`, {
    method: "DELETE",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({confirmProjectId}),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `project delete failed with ${response.status}`);
  }
  return payload;
}
