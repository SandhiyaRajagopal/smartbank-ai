// Thin client for the FastAPI backend. All calls send the JWT from login.

const TOKEN_KEY = 'smartbank_token'

export const auth = {
  get token() {
    try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
  },
  set token(value) {
    try { value ? localStorage.setItem(TOKEN_KEY, value) : localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ }
  },
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* not json */ }
    if (res.status === 401 && path !== '/api/auth/login') window.dispatchEvent(new Event('smartbank:logout'))
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'Request failed')
  }
  return res.json()
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body ?? {}),
}

/**
 * POST to a Server-Sent-Events endpoint and call onEvent(type, data) for every event
 * as it arrives (trace steps, confirmation, final, error, done).
 */
export async function streamSSE(path, body, onEvent) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* not json */ }
    throw new ApiError(res.status, detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      let type = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) type = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (data) onEvent(type, JSON.parse(data))
    }
  }
}

// The token is sent as the first WebSocket message, never in the URL (URLs end up in server logs).
export function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws`
}

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
export const formatINR = (n) => (n == null ? '—' : inr.format(n))
export const formatTime = (iso) =>
  new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
