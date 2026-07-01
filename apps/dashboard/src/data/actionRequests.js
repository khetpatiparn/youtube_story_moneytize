export async function submitProjectAction(fetchImpl, projectId, action, body) {
  const response = await fetchImpl(`/api/projects/${projectId}/${action}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? `action failed with ${response.status}`);
  }
  return payload;
}
