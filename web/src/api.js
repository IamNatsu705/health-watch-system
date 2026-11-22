const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch { /* keep HTTP status */ }
    throw new Error(detail)
  }
  return response.json()
}

export const api = {
  devices: () => request('/api/v1/devices'),
  latest: (id) => request(`/api/v1/devices/${encodeURIComponent(id)}/latest`),
  history: (id) => request(`/api/v1/devices/${encodeURIComponent(id)}/history?limit=45`),
  events: (id) => request(`/api/v1/devices/${encodeURIComponent(id)}/events?limit=8`),
  activity: (payload) => request('/api/v1/activity', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
}
