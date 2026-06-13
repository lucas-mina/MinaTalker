/**
 * Login + refresh against the internal core API (see Swagger at VITE_INTERNAL_API_BASE + /docs).
 * Persists access (and optional refresh) token for WebRTC /human /asr and internal LLM Bearer auth.
 */

const ACCESS_KEY = 'internal_access_token'
const REFRESH_KEY = 'internal_refresh_token'
const USER_ID_KEY = 'internal_user_id'

const REFRESH_INTERVAL_MS = 10 * 60 * 1000

let refreshTimerId = null

function authRequestTimeoutMs() {
  const raw = import.meta.env.VITE_AUTH_REQUEST_TIMEOUT_MS
  const n = raw != null && String(raw).trim() !== '' ? Number(raw) : 30000
  return Number.isFinite(n) && n > 0 ? n : 30000
}

/**
 * fetch with hard timeout so login UI cannot spin forever on hung TLS/CORS/preflight.
 */
async function fetchWithTimeout(url, init = {}) {
  const timeoutMs = authRequestTimeoutMs()
  const controller = new AbortController()
  const id = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } catch (e) {
    const name = e && e.name
    if (name === 'AbortError') {
      throw new Error(
        `Request timed out after ${Math.round(timeoutMs / 1000)}s — server did not respond (${url}). ` +
          'Check HTTPS/port, firewall, or use dev proxy: VITE_INTERNAL_API_BASE=/internal-core in .env'
      )
    }
    if (e instanceof TypeError) {
      throw new Error(
        `Network/CORS error: ${e.message}. From Vite dev, try VITE_INTERNAL_API_BASE=/internal-core ` +
          'so login goes same-origin through vite.config.js proxy (avoids browser CORS to the ELB).'
      )
    }
    throw e
  } finally {
    window.clearTimeout(id)
  }
}

function trimBase(url) {
  if (!url || typeof url !== 'string') return ''
  return url.replace(/\/+$/, '')
}

function joinUrl(base, path) {
  const b = trimBase(base)
  const p = (path || '').startsWith('/') ? path : `/${path || ''}`
  return `${b}${p}`
}

export function getInternalApiBase() {
  const raw = (import.meta.env.VITE_INTERNAL_API_BASE || '').trim()
  return trimBase(raw)
}

export function isInternalAuthConfigured() {
  return !!getInternalApiBase()
}

export function getStoredAccessToken() {
  const s = sessionStorage.getItem(ACCESS_KEY)
  if (s && s.trim()) return s.trim()
  const l = localStorage.getItem(ACCESS_KEY)
  if (l && l.trim()) return l.trim()
  return ''
}

function getStoredRefreshToken() {
  const s = sessionStorage.getItem(REFRESH_KEY)
  if (s && s.trim()) return s.trim()
  const l = localStorage.getItem(REFRESH_KEY)
  if (l && l.trim()) return l.trim()
  return ''
}

function loginPath() {
  return (import.meta.env.VITE_AUTH_LOGIN_PATH || '/api/auth/login').trim() || '/api/auth/login'
}

function refreshPath() {
  return (import.meta.env.VITE_AUTH_REFRESH_PATH || '/api/auth/refresh').trim() || '/api/auth/refresh'
}

function userField() {
  return (import.meta.env.VITE_AUTH_USER_FIELD || 'username').trim() || 'username'
}

function passField() {
  return (import.meta.env.VITE_AUTH_PASS_FIELD || 'password').trim() || 'password'
}

function persistOptionalLocal(refreshToken) {
  if (import.meta.env.VITE_AUTH_PERSIST === 'local') {
    const access = sessionStorage.getItem(ACCESS_KEY)
    if (access) localStorage.setItem(ACCESS_KEY, access)
    if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken)
  }
}

function extractUserId(json) {
  if (!json || typeof json !== 'object') return null
  const direct = json.user_id ?? json.userId ?? json.id
  if (direct != null && String(direct).trim()) return String(direct).trim()
  const nested = json.user?.id ?? json.user?.user_id ?? json.user?.userId
  if (nested != null && String(nested).trim()) return String(nested).trim()
  return null
}

function extractTokens(json) {
  if (!json || typeof json !== 'object') return null
  const access = json.access_token ?? json.accessToken ?? json.token
  if (!access || typeof access !== 'string') return null
  const refresh = json.refresh_token ?? json.refreshToken ?? null
  const userId = extractUserId(json)
  return {
    access: access.trim(),
    refresh: typeof refresh === 'string' ? refresh.trim() : null,
    userId,
  }
}

export function persistTokens({ access, refresh, userId }) {
  if (access) sessionStorage.setItem(ACCESS_KEY, access)
  else sessionStorage.removeItem(ACCESS_KEY)
  if (refresh) sessionStorage.setItem(REFRESH_KEY, refresh)
  else sessionStorage.removeItem(REFRESH_KEY)
  if (userId) sessionStorage.setItem(USER_ID_KEY, userId)
  else sessionStorage.removeItem(USER_ID_KEY)
  persistOptionalLocal(refresh)
}

export function clearInternalAuth() {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(USER_ID_KEY)
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_ID_KEY)
  sessionStorage.removeItem('internal_auth_skip')
}

export function getStoredUserId() {
  const s = sessionStorage.getItem(USER_ID_KEY)
  if (s && s.trim()) return s.trim()
  const l = localStorage.getItem(USER_ID_KEY)
  if (l && l.trim()) return l.trim()
  return ''
}

export async function loginInternalAuth(username, password) {
  const base = getInternalApiBase()
  if (!base) throw new Error('VITE_INTERNAL_API_BASE is not set')

  const body = {
    [userField()]: username,
    [passField()]: password,
  }

  const url = joinUrl(base, loginPath())
  if (import.meta.env.DEV || import.meta.env.VITE_DEBUG_INTERNAL_AUTH === 'true') {
    // If you never see this line, the login UI was skipped (token / skip flag) or VITE_INTERNAL_API_BASE is empty in this bundle.
    console.info('[internal-auth] POST', url)
  }
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })

  const text = await res.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    json = null
  }

  if (!res.ok) {
    const msg = json?.detail || json?.message || json?.error || text?.slice(0, 200) || res.statusText
    throw new Error(typeof msg === 'string' ? msg : res.statusText || 'Login failed')
  }

  const tokens = extractTokens(json)
  if (!tokens) throw new Error('Login response missing access_token')
  persistTokens({ access: tokens.access, refresh: tokens.refresh, userId: tokens.userId })
  return tokens
}

export async function refreshInternalAccessToken() {
  const base = getInternalApiBase()
  if (!base) return false

  const rt = getStoredRefreshToken()
  const access = getStoredAccessToken()
  const useBearer = import.meta.env.VITE_AUTH_REFRESH_USE_BEARER === 'true'

  if (!rt && !(useBearer && access)) return false

  const url = joinUrl(base, refreshPath())

  const headers = { Accept: 'application/json' }
  let body = null
  if (useBearer && access) {
    headers.Authorization = `Bearer ${access}`
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify({})
  } else if (rt) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify({ refresh_token: rt })
  } else {
    return false
  }

  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers,
    body,
  })

  const text = await res.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    json = null
  }

  if (!res.ok) {
    clearInternalAuth()
    return false
  }

  const tokens = extractTokens(json)
  if (!tokens?.access) {
    clearInternalAuth()
    return false
  }
  persistTokens({
    access: tokens.access,
    refresh: tokens.refresh || rt,
    userId: tokens.userId || getStoredUserId() || undefined,
  })
  return true
}

/**
 * @param {{ onRefreshFail?: (err: Error) => void }} [hooks]
 */
export function startAuthRefreshLoop(hooks = {}) {
  stopAuthRefreshLoop()
  if (!isInternalAuthConfigured()) return
  const canRotate =
    !!getStoredRefreshToken() ||
    (import.meta.env.VITE_AUTH_REFRESH_USE_BEARER === 'true' && !!getStoredAccessToken())
  if (!canRotate) return

  refreshTimerId = window.setInterval(async () => {
    try {
      const ok = await refreshInternalAccessToken()
      if (!ok && hooks.onRefreshFail) {
        hooks.onRefreshFail(new Error('Session refresh failed; please sign in again'))
      }
    } catch (e) {
      clearInternalAuth()
      if (hooks.onRefreshFail) hooks.onRefreshFail(e instanceof Error ? e : new Error(String(e)))
    }
  }, REFRESH_INTERVAL_MS)
}

export function stopAuthRefreshLoop() {
  if (refreshTimerId != null) {
    clearInterval(refreshTimerId)
    refreshTimerId = null
  }
}

export function useInternalAuth() {
  return {
    getInternalApiBase,
    isInternalAuthConfigured,
    getStoredAccessToken,
    loginInternalAuth,
    refreshInternalAccessToken,
    persistTokens,
    clearInternalAuth,
    startAuthRefreshLoop,
    stopAuthRefreshLoop,
    REFRESH_INTERVAL_MS,
  }
}
