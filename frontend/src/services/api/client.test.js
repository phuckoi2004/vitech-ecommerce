import { afterEach, describe, expect, test, vi } from 'vitest'
import { AuthApiError, apiRequest } from '../../lib/auth-api.js'
import { API_ROOT, ApiError, queryString, request } from './client.js'

function jsonResponse(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...headers } })
}

function mockFetch(response) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async (url, options) => {
    calls.push({ url, ...options })
    return typeof response === 'function' ? response(url, options) : response
  }))
  return calls
}

async function failure(promise) {
  try {
    await promise
  } catch (error) {
    return error
  }
  throw new Error('Expected the request to fail')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('successful responses', () => {
  test('GET by default with credentials, no-store cache, bearer token, CSRF header and query parameters', async () => {
    const calls = mockFetch(jsonResponse({ Items: [], Total: 0 }))
    const data = await request('/products', {
      query: { keyword: 'điện thoại', page: 2, brand_id: undefined, category_id: null, empty: '', tag: ['a', 'b'] },
      accessToken: 'access-for-test',
      csrfToken: 'csrf-for-test',
    })
    expect(data).toEqual({ Items: [], Total: 0 })
    expect(calls).toHaveLength(1)
    const [call] = calls
    expect(call.url).toBe('/api/products?keyword=%C4%91i%E1%BB%87n+tho%E1%BA%A1i&page=2&tag=a&tag=b')
    expect(call.method).toBe('GET')
    expect(call.credentials).toBe('include')
    expect(call.cache).toBe('no-store')
    expect(call.headers).toEqual({
      Accept: 'application/json', Authorization: 'Bearer access-for-test', 'X-CSRF-Token': 'csrf-for-test',
    })
    expect(call.body).toBeUndefined()
  })

  test('JSON body is serialized with a JSON content type; a query extends an existing query string', async () => {
    const calls = mockFetch(jsonResponse({ ok: true }, 201))
    await request('/cart/items?source=test', { method: 'POST', body: { ProductVariantId: 'v1', Quantity: 2 }, query: { page: 1 } })
    expect(calls[0].url).toBe('/api/cart/items?source=test&page=1')
    expect(calls[0].method).toBe('POST')
    expect(calls[0].headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(calls[0].body)).toEqual({ ProductVariantId: 'v1', Quantity: 2 })
  })

  test('204 resolves to null without reading a body', async () => {
    const response = new Response(null, { status: 204 })
    const json = vi.spyOn(response, 'json')
    mockFetch(response)
    expect(await request('/users/me/addresses/1', { method: 'DELETE' })).toBeNull()
    expect(json).not.toHaveBeenCalled()
  })

  test('a file is sent as-is with its own content type', async () => {
    const calls = mockFetch(jsonResponse({ AvatarUrl: 'https://cdn.example/avatar.png' }))
    const file = new Blob(['image'], { type: 'image/png' })
    await request('/users/me/avatar', { method: 'PUT', file })
    expect(calls[0].body).toBe(file)
    expect(calls[0].headers['Content-Type']).toBe('image/png')
  })

  test('the default API root is /api and queryString skips empty values', () => {
    expect(API_ROOT).toBe('/api')
    expect(queryString({ a: '', b: null, c: undefined })).toBe('')
    expect(queryString({ include_deleted: false, page: 0 })).toBe('?include_deleted=false&page=0')
  })
})

describe('errors', () => {
  test('422 lists Vietnamese messages per field and never echoes the submitted input', async () => {
    mockFetch(jsonResponse({ detail: [
      { loc: ['body', 'Email'], msg: 'value is not a valid email address', type: 'value_error', input: 'secret-input' },
      { loc: ['body', 'Items', 0, 'Quantity'], msg: 'Input should be greater than 0', type: 'greater_than', input: -1 },
      { loc: ['query', 'page'], msg: 'Field required', type: 'missing' },
    ] }, 422))
    const error = await failure(request('/orders', { method: 'POST', body: {} }))
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(422)
    expect(error.code).toBeNull()
    expect(error.detail).toBeNull()
    expect(error.fieldErrors).toEqual({
      Email: 'Vui lòng nhập email hợp lệ.',
      'Items.0.Quantity': 'Thông tin không hợp lệ. Vui lòng kiểm tra lại.',
      page: 'Thông tin không được để trống.',
    })
    expect(error.message).toBe('Vui lòng nhập email hợp lệ. Thông tin không hợp lệ. Vui lòng kiểm tra lại. Thông tin không được để trống.')
    expect(JSON.stringify({ ...error, message: error.message })).not.toContain('secret-input')
  })

  test.each([
    [409, 'insufficient_stock', 'Sản phẩm không đủ số lượng trong kho'],
    [400, 'coupon_invalid', 'Mã giảm giá không hợp lệ'],
  ])('a business error keeps its code (%i %s)', async (status, code, detail) => {
    mockFetch(jsonResponse({ detail, code }, status))
    const error = await failure(request('/orders', { method: 'POST', body: {} }))
    expect(error).toMatchObject({ status, code, detail, message: detail, fieldErrors: {}, retryAfter: null })
  })

  test('an error with only a detail has no code; its Vietnamese text is the message', async () => {
    mockFetch(jsonResponse({ detail: 'Cần đăng nhập' }, 401, { 'WWW-Authenticate': 'Bearer' }))
    const error = await failure(request('/users/me'))
    expect(error).toMatchObject({ status: 401, code: null, detail: 'Cần đăng nhập', message: 'Cần đăng nhập' })
  })

  test('403 without a Vietnamese detail uses a neutral message, not the admin-only one', async () => {
    mockFetch(jsonResponse({ detail: 'Forbidden' }, 403))
    const error = await failure(request('/cart'))
    expect(error.status).toBe(403)
    expect(error.detail).toBe('Forbidden')
    expect(error.message).toBe('Bạn không có quyền thực hiện thao tác này.')
    expect(error.message).not.toMatch(/quản trị/)
  })

  test('429 exposes Retry-After; 5xx and network failures give safe messages', async () => {
    mockFetch(jsonResponse({ detail: 'Too Many Requests' }, 429, { 'Retry-After': '42' }))
    expect(await failure(request('/auth/login', { method: 'POST', body: {} }))).toMatchObject({
      status: 429, retryAfter: 42, message: 'Bạn đã thử quá nhiều lần. Vui lòng chờ rồi thử lại.',
    })
    mockFetch(jsonResponse({ detail: 'Internal Server Error' }, 500))
    expect((await failure(request('/products'))).message).toBe('Hệ thống đang bận. Vui lòng thử lại sau.')
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('private transport diagnostics') }))
    const offline = await failure(request('/products'))
    expect(offline.status).toBe(0)
    expect(offline.message).toMatch(/Không kết nối được máy chủ/)
    expect(offline.message).not.toContain('private')
  })

  test('a successful response with an invalid body is an error', async () => {
    mockFetch(new Response('not json', { status: 200 }))
    expect(await failure(request('/products'))).toMatchObject({ status: 200, message: 'Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại.' })
  })

  test('requests are not retried by the client', async () => {
    const calls = mockFetch(jsonResponse({ detail: 'Internal Server Error' }, 500))
    await failure(request('/orders', { method: 'POST', body: {} }))
    expect(calls).toHaveLength(1)
  })
})

describe('compatibility layer', () => {
  test('auth-api keeps AuthApiError and the POST default of apiRequest', async () => {
    expect(AuthApiError).toBe(ApiError)
    const calls = mockFetch(() => jsonResponse({ ok: true }))
    await apiRequest('/auth/change-password', { body: { CurrentPassword: 'x' }, accessToken: 'access-for-test' })
    await apiRequest('/users/me', { method: 'GET', accessToken: 'access-for-test' })
    expect(calls.map((call) => call.method)).toEqual(['POST', 'GET'])
  })
})
