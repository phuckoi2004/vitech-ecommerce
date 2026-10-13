// Auth endpoints and the refresh-cookie rotation. HTTP and error handling come from the shared client;
// this module keeps its original exports so existing pages, API modules and tests keep working.
import { ApiError as AuthApiError, request as sendRequest } from '../services/api/client.js'

export { AuthApiError }

const INTERNAL_ROLES = new Set(['Staff', 'Admin'])
let refreshRequest = null
let internalRefresh = null
let refreshController = null

export function readCsrfToken() {
  if (typeof document === 'undefined') return ''
  const entry = document.cookie.split(';').find((item) => item.trim().startsWith('vietech_csrf='))
  if (!entry) return ''
  try {
    return decodeURIComponent(entry.trim().slice('vietech_csrf='.length))
  } catch {
    return ''
  }
}

export function clearLocalCsrf() {
  cancelPendingRefresh()
  if (typeof document === 'undefined') return
  const secure = globalThis.location?.protocol === 'https:' ? '; Secure' : ''
  // The refresh cookie is HttpOnly; discard its readable companion so an
  // offline logout cannot silently restore the previous session on reload.
  document.cookie = `vietech_csrf=; Path=/; Max-Age=0; SameSite=Lax${secure}`
}

// Compatibility entry point for the account modules: same options as before and POST unless `method` is given.
// New code should use `request` from services/api/client.js, which defaults to GET and accepts `query`.
export function apiRequest(path, options = {}) {
  return sendRequest(path, { ...options, method: options.method ?? 'POST' })
}

function request(path, options) {
  return apiRequest(`/auth${path}`, options)
}

function requireInternalUser(data) {
  if (!INTERNAL_ROLES.has(data?.user?.Role)) {
    throw new AuthApiError('Trang này chỉ dành cho quản trị viên và nhân viên.', 403)
  }
  return data
}

function requireSession(data) {
  requireInternalUser(data)
  if (!data.access_token || !data.csrf_token || !Array.isArray(data.permissions)) {
    throw new AuthApiError('Thông tin phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.')
  }
  return data
}

export async function loginInternal(identifier, password) {
  cancelPendingRefresh()
  return requireSession(await request('/login', {
    body: { Identifier: identifier.trim(), Password: password, Portal: 'admin' },
  }))
}

export function requestPasswordReset(identifier) {
  return request('/forgot-password', { body: { Identifier: identifier.trim() } })
}

export function verifyPasswordReset(challengeId, code) {
  return request('/reset-password/verify', { body: { ChallengeId: challengeId, Code: code.trim() } })
}

export function setNewPassword(resetToken, newPassword, confirmPassword) {
  return request('/reset-password', {
    body: { ResetToken: resetToken, NewPassword: newPassword, ConfirmPassword: confirmPassword },
  })
}

// Customer sign-in. The backend refuses Staff/Admin accounts on the customer portal.
export async function loginCustomer(identifier, password) {
  cancelPendingRefresh()
  const data = await request('/login', { body: { Identifier: identifier.trim(), Password: password, Portal: 'customer' } })
  if (data?.user?.Role !== 'Customer' || !data.access_token) {
    throw new AuthApiError('Tài khoản này không dùng để mua hàng trên website.', 403)
  }
  return data
}

// Customer sign-up: the account is created only after the emailed OTP is verified.
export function registerCustomer({ FullName, Email, PhoneNumber, Password, ConfirmPassword }) {
  return request('/register', {
    body: { FullName: FullName.trim(), Email: Email.trim(), PhoneNumber: PhoneNumber.trim(), Password, ConfirmPassword },
  })
}

export function verifyRegistration(challengeId, code) {
  return request('/register/verify', { body: { ChallengeId: challengeId, Code: code.trim() } })
}

export function resendOtp(challengeId) {
  return request('/otp/resend', { body: { ChallengeId: challengeId } })
}

// Refresh rotates a single-use cookie shared by the customer site and the internal area.
// Share one request across StrictMode effects and callers so a second request cannot
// replay the previous refresh token.
export function cancelPendingRefresh() {
  // A response from the previous session must not replace cookies from a new one.
  const pendingController = refreshController
  refreshRequest = null
  internalRefresh = null
  refreshController = null
  pendingController?.abort()
}

function rotateRefresh() {
  if (refreshRequest) return refreshRequest
  const csrfToken = readCsrfToken()
  if (!csrfToken) return Promise.reject(new AuthApiError('Vui lòng đăng nhập để tiếp tục.', 401))
  const controller = new AbortController()
  const pending = request('/refresh', { csrfToken, signal: controller.signal }).finally(() => {
    // An aborted request may finish after another rotation has already started.
    if (refreshRequest !== pending) return
    refreshRequest = null
    internalRefresh = null
    refreshController = null
  })
  refreshRequest = pending
  refreshController = controller
  return pending
}

export function refreshSession() {
  if (internalRefresh) return internalRefresh
  const pending = rotateRefresh()
  const session = pending.then(requireSession)
  if (pending === refreshRequest) internalRefresh = session
  return session
}

// A renewed session of any supported role: Customer, or Staff/Admin with the internal session fields.
// Other roles are refused (403), like the portal checks above.
function requireKnownSession(data) {
  const role = data?.user?.Role
  if (INTERNAL_ROLES.has(role)) return requireSession(data)
  if (role !== 'Customer') throw new AuthApiError('Tài khoản không được phép truy cập trang này.', 403)
  if (!data.access_token) throw new AuthApiError('Thông tin phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.')
  return data
}

// Rotates the shared refresh cookie for whichever portal owns it. Overlapping callers share one request.
// Rejects with 401 when there is no CSRF cookie, without a network request.
export function renewSession() {
  return rotateRefresh().then(requireKnownSession)
}

// Startup restore for the whole app: the current session, or null when there is none (no cookie, expired, revoked).
export async function restoreSession() {
  if (!readCsrfToken()) return null
  try {
    return await renewSession()
  } catch (failure) {
    if ([401, 403].includes(failure.status)) return null
    throw failure
  }
}

// Customer site: the signed-in customer, or null when there is no customer session
// (signed out, expired, or a Staff/Admin session in this browser).
export async function restoreCustomerSession() {
  if (!readCsrfToken()) return null
  try {
    const data = await rotateRefresh()
    return data?.user?.Role === 'Customer' && data.access_token ? data : null
  } catch (failure) {
    if ([401, 403].includes(failure.status)) return null
    throw failure
  }
}

export async function getCurrentUser(accessToken) {
  return requireInternalUser(await request('/me', { method: 'GET', accessToken }))
}

export function logoutSession(accessToken, csrfToken) {
  cancelPendingRefresh()
  // Prefer the current cookie because another refresh may have rotated it.
  return request('/logout', { accessToken, csrfToken: readCsrfToken() || csrfToken })
}
