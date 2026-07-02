async function parseJson(response) {
  return response.json().catch(() => ({}));
}

export async function runProjectJob(fetchImpl, projectId, operation) {
  const response = await fetchImpl(`/api/projects/${projectId}/${operation}`, {
    method: "POST",
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `job request failed with ${response.status}`);
  }
  return payload;
}

export async function loadJobs(fetchImpl, projectId) {
  const response = await fetchImpl(`/api/jobs?projectId=${projectId}`);
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `jobs request failed with ${response.status}`);
  }
  return payload;
}

export async function loadJob(fetchImpl, jobId) {
  const response = await fetchImpl(`/api/jobs/${jobId}`);
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `job request failed with ${response.status}`);
  }
  return payload;
}

export async function cancelJob(fetchImpl, jobId) {
  const response = await fetchImpl(`/api/jobs/${jobId}/cancel`, {
    method: "POST",
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `job cancel failed with ${response.status}`);
  }
  return payload;
}
