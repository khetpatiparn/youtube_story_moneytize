export async function loadProjectEvents(fetchImpl, projectId) {
  const response = await fetchImpl(`/api/projects/${projectId}/events`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? `events request failed with ${response.status}`);
  }
  return {events: Array.isArray(payload.events) ? payload.events : []};
}
