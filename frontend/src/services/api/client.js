// Shared HTTP client for the VieTech backend.
//
// Error bodies from the backend:
// - business rules (ServiceError): {"detail": "<Vietnamese message>", "code": "<machine code>"}
// - account/auth (AuthError) and framework errors: {"detail": "<message>"}
// - request validation (422): {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}
// Requests are never retried here; session refresh and the single retry after a 401 live in the AuthProvider.

export const API_ROOT = (import.meta.env?.VITE_API_URL || '/api').replace(/\/+$/, '')

export class ApiError extends Error {
  // Positional arguments keep the original AuthApiError(message, status, retryAfter) signature.
  constructor(message, status = 0, retryAfter = null, { code = null, detail = null, fieldErrors = {} } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
    this.code = code
    this.detail = detail
    this.fieldErrors = fieldErrors
  }
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
  Name: 'Tên',
  Slug: 'Đường dẫn',
  CategoryId: 'Danh mục',
  BrandId: 'Thương hiệu',
  WarrantyMonths: 'Số tháng bảo hành',
  Specifications: 'Thông số kỹ thuật',
  Sku: 'SKU',
  VariantName: 'Tên biến thể',
  Color: 'Màu sắc',
  Storage: 'Dung lượng',
  Images: 'Ảnh sản phẩm',
  Price: 'Giá bán',
  MinStockLevel: 'Ngưỡng cảnh báo tồn',
  ImageUrl: 'Đường dẫn ảnh',
}

// FastAPI prefixes the location with where the value came from.
const LOCATION_SOURCES = new Set(['body', 'query', 'path', 'header', 'cookie'])

// Our own messages are Vietnamese (always non-ASCII); plain-ASCII text is a framework default in English.
function isVietnamese(message) {
  return Array.from(message).some((character) => character.codePointAt(0) > 127)
}

// One validation entry as a Vietnamese sentence. The submitted `input` is never used: it may be a password or OTP.
function itemMessage(item) {
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
}

function validationMessage(details) {
  return details.slice(0, 3).map(itemMessage).join(' ')
}

// {"Email": "...", "Items.0.Quantity": "..."}; the first message wins for each field.
function fieldErrorsFrom(details) {
  const errors = {}
  for (const item of details) {
    const loc = Array.isArray(item?.loc) ? item.loc : []
    const key = (LOCATION_SOURCES.has(loc[0]) ? loc.slice(1) : loc).join('.') || '_'
    if (!(key in errors)) errors[key] = itemMessage(item)
  }
  return errors
}

function errorMessage(status, body) {
  if (status === 422 && Array.isArray(body?.detail)) return validationMessage(body.detail)
  if (typeof body?.detail === 'string' && isVietnamese(body.detail)) return body.detail
  if (status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  if (status === 403) return 'Bạn không có quyền thực hiện thao tác này.'
  if (status === 404) return 'Không tìm thấy chức năng yêu cầu. Vui lòng tải lại trang.'
  if (status === 429) return 'Bạn đã thử quá nhiều lần. Vui lòng chờ rồi thử lại.'
  if (status >= 500) return 'Hệ thống đang bận. Vui lòng thử lại sau.'
  return 'Không thể hoàn tất yêu cầu. Vui lòng thử lại.'
}

export function errorFromResponse(status, body, headers) {
  const retry = headers?.get?.('Retry-After') ?? null
  const retryAfter = retry !== null && /^\d+$/.test(retry) ? Number(retry) : null
  const details = status === 422 && Array.isArray(body?.detail) ? body.detail : null
  return new ApiError(errorMessage(status, body), status, retryAfter, {
    code: typeof body?.code === 'string' ? body.code : null,
    detail: typeof body?.detail === 'string' ? body.detail : null,
    fieldErrors: details ? fieldErrorsFrom(details) : {},
  })
}

// Skips undefined, null and empty strings; arrays repeat the key.
export function queryString(query) {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item === undefined || item === null || item === '') continue
      params.append(key, String(item))
    }
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

function withQuery(path, query) {
  const search = queryString(query)
  if (!search) return path
  return path.includes('?') ? `${path}&${search.slice(1)}` : `${path}${search}`
}

// `body` is sent as JSON; `file` is sent as-is with its own type (avatar upload). 204 resolves to null.
export async function request(path, { method = 'GET', query, body, file, accessToken, csrfToken, signal } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (file !== undefined) headers['Content-Type'] = file.type || 'application/octet-stream'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken

  let response
  try {
    response = await fetch(`${API_ROOT}${withQuery(path, query)}`, {
      method,
      credentials: 'include',
      cache: 'no-store',
      headers,
      ...(signal ? { signal } : {}),
      ...(file !== undefined ? { body: file } : body === undefined ? {} : { body: JSON.stringify(body) }),
    })
  } catch {
    signal?.throwIfAborted()
    throw new ApiError('Không kết nối được máy chủ. Vui lòng kiểm tra kết nối và thử lại.')
  }

  signal?.throwIfAborted()
  if (response.status === 204) return null
  let data
  try {
    data = await response.json()
  } catch {
    signal?.throwIfAborted()
    if (response.ok) throw new ApiError('Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại.', response.status)
  }
  signal?.throwIfAborted()
  if (!response.ok) throw errorFromResponse(response.status, data, response.headers)
  return data
}
