// 서버와 말하는 곳은 이 파일 하나. 쿠키(sid)는 브라우저가 알아서 붙인다 — 코드에 토큰이 없다.
async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (res.status === 204) return null
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    throw Object.assign(new Error(detail || `HTTP ${res.status}`), { status: res.status })
  }
  return body
}

export const api = {
  me: () => request('/api/me'),
  login: (username, password) => request('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  register: (username, password) => request('/api/register', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => request('/api/logout', { method: 'POST' }),
  eta: (distance_km, pending_orders) => request('/api/eta', { method: 'POST', body: JSON.stringify({ distance_km, pending_orders }) }),
  orders: () => request('/api/orders'),
}
