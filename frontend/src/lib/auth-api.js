const API_ROOT = (import.meta.env?.VITE_API_URL || '/api').replace(/\/+$/, '')
const INTERNAL_ROLES = new Set(['Staff', 'Admin'])
let refreshRequest = null
let internalRefresh = null
let refreshController = null

export class AuthApiError extends Error {
  constructor(message, status = 0, retryAfter = null) {
    super(message)
    this.name = 'AuthApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

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

const FIELD_NAMES = {
  Identifier: 'Số điện thoại / Email',
  Password: 'Mật khẩu',
  ChallengeId: 'Yêu cầu xác minh',
  Code: 'Mã OTP',
  NewPassword: 'Mật khẩu mới',
  ConfirmPassword: 'Xác nhận mật khẩu',
  ResetToken: 'Yêu cầu đặt lại mật khẩu',
  CurrentPassword: 'Mật khẩu hiện tại',
  FullName: 'Họ và tên',
  PhoneNumber: 'Số điện thoại',
  Gender: 'Giới tính',
  DateOfBirth: 'Ngày sinh',
  Province: 'Tỉnh/Thành phố',
  Ward: 'Phường/Xã',
  DetailAddress: 'Địa chỉ chi tiết',
  Email: 'Email',
  LockReason: 'Lý do khóa',
  LockedUntil: 'Thời hạn khóa',
  search: 'Từ khóa tìm kiếm',
}

// Our own messages are Vietnamese (always non-ASCII); plain-ASCII text is a framework default in English.
function isVietnamese(message) {
  return Array.from(message).some((character) => character.codePointAt(0) > 127)
}

function validationMessage(details) {
  return details.slice(0, 3).map((item) => {
    const field = item.loc?.at(-1)
    const label = FIELD_NAMES[field] || 'Thông tin'
    const message = typeof item.msg === 'string' ? item.msg.replace(/^Value error,\s*/, '') : ''
    if (isVietnamese(message)) return message
    if (item.type === 'missing' || item.type === 'string_too_short') return `${label} không được để trống.`
    if (field === 'Code') return 'Mã OTP gồm 6 chữ số.'
    if (field === 'Email') return 'Vui lòng nhập email hợp lệ.'
    if (field === 'PhoneNumber') return 'Vui lòng nhập số điện thoại Việt Nam hợp lệ.'
    if (field === 'Identifier') return 'Vui lòng nhập số điện thoại Việt Nam hoặc email hợp lệ.'
    if (field === 'ChallengeId' || field === 'ResetToken') return 'Yêu cầu xác minh không hợp lệ. Vui lòng gửi lại mã OTP.'
    return `${label} không hợp lệ. Vui lòng kiểm tra lại.`
  }).join(' ')
}

function errorMessage(status, body) {
  if (status === 422 && Array.isArray(body?.detail)) return validationMessage(body.detail)
  if (typeof body?.detail === 'string' && isVietnamese(body.detail)) return body.detail
  if (status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  if (status === 403) return 'Tài khoản không được phép truy cập trang quản trị.'
  if (status === 404) return 'Không tìm thấy chức năng yêu cầu. Vui lòng tải lại trang.'
  if (status === 429) return 'Bạn đã thử quá nhiều lần. Vui lòng chờ rồi thử lại.'
  if (status >= 500) return 'Hệ thống đang bận. Vui lòng thử lại sau.'
  return 'Không thể hoàn tất yêu cầu. Vui lòng thử lại.'
}

// `body` is sent as JSON; `file` is sent as-is with its own type (avatar upload).
export async function apiRequest(path, { method = 'POST', body, file, accessToken, csrfToken, signal } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (file !== undefined) headers['Content-Type'] = file.type || 'application/octet-stream'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken

  let response
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      method,
      credentials: 'include',
      cache: 'no-store',
      headers,
      ...(signal ? { signal } : {}),
      ...(file !== undefined ? { body: file } : body === undefined ? {} : { body: JSON.stringify(body) }),
    })
  } catch {
    signal?.throwIfAborted()
    throw new AuthApiError('Không kết nối được máy chủ. Vui lòng kiểm tra kết nối và thử lại.')
  }

  signal?.throwIfAborted()
  if (response.status === 204) return null
  let data
  try {
    data = await response.json()
  } catch {
    signal?.throwIfAborted()
    if (response.ok) throw new AuthApiError('Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại.', response.status)
  }
  signal?.throwIfAborted()
  if (!response.ok) {
    const retry = response.headers.get('Retry-After')
    const retryAfter = retry !== null && /^\d+$/.test(retry) ? Number(retry) : null
    throw new AuthApiError(errorMessage(response.status, data), response.status, retryAfter)
  }
  return data
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
