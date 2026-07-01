export async function loadDashboardProjectsFromApi(fetchImpl = fetch) {
  const response = await fetchImpl("/api/projects");
  if (!response.ok) {
    throw new Error(`dashboard api returned ${response.status}`);
  }

  const payload = await response.json();
  return {
    projects: Array.isArray(payload.projects) ? payload.projects : [],
  };
}
