async function parseJson(response) {
  return response.json().catch(() => ({}));
}

export async function loadSettings(fetchImpl = fetch) {
  const response = await fetchImpl("/api/settings");
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `settings request failed with ${response.status}`);
  }
  return payload;
}

export async function saveSettings(fetchImpl, input) {
  const response = await fetchImpl("/api/settings", {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(input),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `settings save failed with ${response.status}`);
  }
  return payload;
}

export async function testProviderSettings(fetchImpl, provider) {
  const response = await fetchImpl("/api/settings/test", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({provider}),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? `settings test failed with ${response.status}`);
  }
  return payload;
}
