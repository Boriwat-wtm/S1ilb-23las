const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

const TOKEN_KEY = 'bank.token'
const USER_KEY = 'bank.user'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function storeSession(token, user) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } catch {
    /* private mode / storage full — the session just won't survive a reload */
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch {
    /* ignore */
  }
}

/** Thrown for every non-2xx response so callers get one shape to handle. */
export class ApiError extends Error {
  constructor(status, detail, body) {
    super(typeof detail === 'string' ? detail : detail?.message || `HTTP ${status}`)
    this.status = status
    this.detail = detail
    this.body = body
  }
}

let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

export async function api(path, { method = 'GET', body, formData, signal, auth = true } = {}) {
  const headers = {}
  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    // Render asleep, no signal, or CORS blocked — all look identical here.
    throw new ApiError(0, 'ต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่')
  }

  if (res.status === 401) {
    // On iOS a standalone PWA can have its localStorage evicted, so an expired
    // or vanished token is a normal event, not an error worth showing.
    clearSession()
    onUnauthorized()
    throw new ApiError(401, 'หมดเวลาเข้าสู่ระบบ กรุณาเข้าใหม่')
  }

  if (res.status === 204) return null

  const text = await res.text()
  let parsed = null
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = text
    }
  }

  if (!res.ok) {
    throw new ApiError(res.status, parsed?.detail ?? parsed ?? res.statusText, parsed)
  }
  return parsed
}

// --- endpoints -------------------------------------------------------------

export const apiHealth = (signal) => api('/health', { auth: false, signal })

export const apiLogin = (username, password) =>
  api('/auth/login', { method: 'POST', auth: false, body: { username, password } })

export const apiMe = () => api('/auth/me')
export const apiUsers = () => api('/auth/users')
export const apiCategories = () => api('/categories')

export const apiSuggestCategory = (text, signal) =>
  api(`/categories/suggest?text=${encodeURIComponent(text)}`, { signal })

export function apiTransactions(filters = {}) {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v !== null && v !== undefined && v !== '') params.set(k, v)
  }
  const qs = params.toString()
  return api(`/transactions${qs ? `?${qs}` : ''}`)
}

export const apiSummary = (month) => api(`/transactions/summary?month=${month}`)
export const apiTransaction = (id) => api(`/transactions/${id}`)
export const apiCreateTransaction = (payload) =>
  api('/transactions', { method: 'POST', body: payload })
export const apiUpdateTransaction = (id, payload) =>
  api(`/transactions/${id}`, { method: 'PUT', body: payload })
export const apiDeleteTransaction = (id) => api(`/transactions/${id}`, { method: 'DELETE' })
export const apiSlipUrl = (id) => api(`/transactions/${id}/slip`)

export function apiUploadSlip(file) {
  const fd = new FormData()
  fd.append('file', file)
  return api('/slips/upload', { method: 'POST', formData: fd })
}

export function exportCsvUrl(filters = {}) {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v !== null && v !== undefined && v !== '') params.set(k, v)
  }
  return `${BASE}/transactions/export.csv?${params.toString()}`
}

/** CSV needs the auth header, so it is fetched as a blob rather than linked. */
export async function downloadCsv(filters = {}) {
  const token = getToken()
  const res = await fetch(exportCsvUrl(filters), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new ApiError(res.status, 'ดาวน์โหลด CSV ไม่สำเร็จ')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `bank-${filters.month || 'all'}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
