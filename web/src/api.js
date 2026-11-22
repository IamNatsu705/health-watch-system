let base = (localStorage.getItem('health-watch-api-base') || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export const isNativeApp = Boolean(window.Capacitor?.isNativePlatform?.())
export const getApiBase = () => base
export function setApiBase(value) {
  base = value.trim().replace(/\/$/, '')
  if (base) localStorage.setItem('health-watch-api-base', base)
  else localStorage.removeItem('health-watch-api-base')
}

async function request(path, options = {}) {
  if (isNativeApp && !base) {
    throw new Error('Chưa cấu hình địa chỉ API trên máy tính')
  }
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
  remoteAlert: (id, active, durationS = 10) => request(
    `/api/v1/devices/${encodeURIComponent(id)}/commands/remote-alert`,
    {
      method: 'POST',
      body: JSON.stringify({ active, duration_s: durationS }),
    },
  ),
  activity: (payload) => request('/api/v1/activity', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
}
