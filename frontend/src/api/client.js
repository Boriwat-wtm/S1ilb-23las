const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

const TOKEN_KEY = 'bank.token'
const USER_KEY = 'bank.user'
const LEDGER_KEY = 'bank.ledger'

const safeGet = (k) => {
  try {
    return localStorage.getItem(k)
  } catch {
    return null
  }
}
const safeSet = (k, v) => {
  try {
    localStorage.setItem(k, v)
  } catch {
    /* private mode or storage full — the session just won't survive a reload */
  }
}
const safeDel = (k) => {
  try {
    localStorage.removeItem(k)
  } catch {
    /* ignore */
  }
}

export const getToken = () => safeGet(TOKEN_KEY)

export function getStoredUser() {
  const raw = safeGet(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function storeSession(token, user) {
  safeSet(TOKEN_KEY, token)
  safeSet(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  safeDel(TOKEN_KEY)
  safeDel(USER_KEY)
  safeDel(LEDGER_KEY)
}

export const getLastLedgerId = () => {
  const raw = safeGet(LEDGER_KEY)
  return raw ? Number(raw) : null
}
export const rememberLedgerId = (id) => safeSet(LEDGER_KEY, String(id))

/** One shape for every non-2xx response so callers have one thing to handle. */
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
    // Render asleep, no signal, or CORS blocked — indistinguishable from here.
    throw new ApiError(0, 'ต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่')
  }

  if (res.status === 401) {
    // On iOS a standalone PWA can have its localStorage evicted, so a token
    // that has simply vanished is routine, not an error worth dramatising.
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
    let detail = parsed?.detail ?? parsed ?? res.statusText
    // FastAPI validation errors arrive as a list; surface the first message
    // rather than "[object Object]".
    if (Array.isArray(detail)) detail = detail[0]?.msg?.replace(/^Value error, /, '') ?? 'ข้อมูลไม่ถูกต้อง'
    throw new ApiError(res.status, detail, parsed)
  }
  return parsed
}

function qs(params = {}) {
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') search.set(k, v)
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

// --- meta / auth -----------------------------------------------------------
export const apiHealth = (signal) => api('/health', { auth: false, signal })

export const apiLogin = (username, password) =>
  api('/auth/login', { method: 'POST', auth: false, body: { username, password } })

export const apiRegister = (username, display_name, password) =>
  api('/auth/register', {
    method: 'POST',
    auth: false,
    body: { username, display_name, password },
  })

export const apiMe = () => api('/auth/me')

// --- ledgers ---------------------------------------------------------------
export const apiLedgers = (includeArchived = false) =>
  api(`/ledgers${qs({ include_archived: includeArchived || '' })}`)

export const apiLedger = (id) => api(`/ledgers/${id}`)
export const apiCreateLedger = (payload) => api('/ledgers', { method: 'POST', body: payload })
export const apiUpdateLedger = (id, payload) =>
  api(`/ledgers/${id}`, { method: 'PATCH', body: payload })
export const apiDeleteLedger = (id) => api(`/ledgers/${id}`, { method: 'DELETE' })

// --- members ---------------------------------------------------------------
export const apiMembers = (ledgerId) => api(`/ledgers/${ledgerId}/members`)
export const apiInvite = (ledgerId, username, role) =>
  api(`/ledgers/${ledgerId}/members`, { method: 'POST', body: { username, role } })
export const apiSetMemberRole = (ledgerId, memberId, role) =>
  api(`/ledgers/${ledgerId}/members/${memberId}`, { method: 'PATCH', body: { role } })
export const apiRemoveMember = (ledgerId, memberId) =>
  api(`/ledgers/${ledgerId}/members/${memberId}`, { method: 'DELETE' })

// --- categories ------------------------------------------------------------
export const apiCategories = (ledgerId) => api(`/ledgers/${ledgerId}/categories`)
export const apiSuggestCategory = (ledgerId, text, signal) =>
  api(`/ledgers/${ledgerId}/categories/suggest${qs({ text })}`, { signal })

// --- entries ---------------------------------------------------------------
export const apiEntries = (ledgerId, filters = {}) =>
  api(`/ledgers/${ledgerId}/entries${qs(filters)}`)
export const apiEntry = (ledgerId, entryId) => api(`/ledgers/${ledgerId}/entries/${entryId}`)
export const apiCreateEntry = (ledgerId, payload) =>
  api(`/ledgers/${ledgerId}/entries`, { method: 'POST', body: payload })
export const apiUpdateEntry = (ledgerId, entryId, payload) =>
  api(`/ledgers/${ledgerId}/entries/${entryId}`, { method: 'PUT', body: payload })
export const apiDeleteEntry = (ledgerId, entryId) =>
  api(`/ledgers/${ledgerId}/entries/${entryId}`, { method: 'DELETE' })
export const apiSlipUrl = (ledgerId, entryId) =>
  api(`/ledgers/${ledgerId}/entries/${entryId}/slip`)
export const apiSummary = (ledgerId, month) =>
  api(`/ledgers/${ledgerId}/entries/summary${qs({ month })}`)

export function apiUploadSlip(ledgerId, file) {
  const fd = new FormData()
  fd.append('file', file)
  return api(`/ledgers/${ledgerId}/slips/upload`, { method: 'POST', formData: fd })
}

/** CSV needs the auth header, so it is fetched as a blob rather than linked. */
export async function downloadCsv(ledgerId, ledgerName, filters = {}) {
  const token = getToken()
  const res = await fetch(`${BASE}/ledgers/${ledgerId}/entries/export.csv${qs(filters)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new ApiError(res.status, 'ดาวน์โหลด CSV ไม่สำเร็จ')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${ledgerName || 'ledger'}-${filters.month || 'all'}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
