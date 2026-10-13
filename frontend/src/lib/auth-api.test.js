// @vitest-environment node
// Uses its own minimal `document`/`location` doubles (jsdom keeps only the first cookie of a multi-cookie assignment).
import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'vitest'
import {
  AuthApiError, cancelPendingRefresh, clearLocalCsrf, getCurrentUser, loginCustomer, loginInternal, logoutSession, readCsrfToken,
  refreshSession, registerCustomer, requestPasswordReset, resendOtp, restoreCustomerSession, setNewPassword,
  verifyPasswordReset, verifyRegistration,
} from './auth-api.js'

const originalFetch = globalThis.fetch
const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
const originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location')
const internalSession = {
  access_token: 'access-for-test',
  csrf_token: 'csrf-for-test',
  expires_in: 900,
  permissions: ['accounts.read'],
  user: { Role: 'Admin', FullName: 'Quản trị viên' },
}
let requests

function mockResponse(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function deferred() {
  let resolve, reject
  const promise = new Promise((accept, decline) => { resolve = accept; reject = decline })
  return { promise, resolve, reject }
}

beforeEach(() => {
  requests = []
  Object.defineProperty(globalThis, 'document', {
    value: { cookie: '' }, writable: true, configurable: true,
  })
  Object.defineProperty(globalThis, 'location', {
    value: { protocol: 'http:' }, writable: true, configurable: true,
  })
  globalThis.fetch = async (url, options) => {
    requests.push({ url, ...options })
    return mockResponse(internalSession)
  }
})

afterEach(() => {
  cancelPendingRefresh()
  globalThis.fetch = originalFetch
  if (originalDocument) Object.defineProperty(globalThis, 'document', originalDocument)
  else delete globalThis.document
  if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation)
  else delete globalThis.location
})

test('internal login uses admin portal, trims identifier and preserves password', async () => {
  await loginInternal('  admin@example.com  ', ' Uppercase1! ')
  assert.equal(requests[0].url, '/api/auth/login')
  assert.equal(requests[0].credentials, 'include')
  assert.equal(requests[0].cache, 'no-store')
  assert.deepEqual(JSON.parse(requests[0].body), {
    Identifier: 'admin@example.com', Password: ' Uppercase1! ', Portal: 'admin',
  })
  assert.equal(requests[0].headers['Content-Type'], 'application/json')
})

test('password recovery posts the exact backend contracts', async () => {
  await requestPasswordReset(' admin@example.com ')
  await verifyPasswordReset('challenge-for-test', ' 123456 ')
  await setNewPassword('reset-for-test', ' NewPass1! ', ' NewPass1! ')
  await resendOtp('challenge-for-test')
  assert.deepEqual(requests.map((entry) => entry.url), [
    '/api/auth/forgot-password', '/api/auth/reset-password/verify',
    '/api/auth/reset-password', '/api/auth/otp/resend',
  ])
  assert.deepEqual(requests.map((entry) => JSON.parse(entry.body)), [
    { Identifier: 'admin@example.com' },
    { ChallengeId: 'challenge-for-test', Code: '123456' },
    { ResetToken: 'reset-for-test', NewPassword: ' NewPass1! ', ConfirmPassword: ' NewPass1! ' },
    { ChallengeId: 'challenge-for-test' },
  ])
})

test('refresh reads only the exact CSRF cookie and shares overlapping rotations', async () => {
  document.cookie = 'other_vietech_csrf=wrong; vietech_csrf=csrf%2Bcurrent; theme=light'
  assert.equal(readCsrfToken(), 'csrf+current')
  let release
  globalThis.fetch = (url, options) => {
    requests.push({ url, ...options })
    return new Promise((resolve) => { release = resolve })
  }
  const first = refreshSession()
  const second = refreshSession()
  assert.strictEqual(first, second)
  assert.equal(requests.length, 1)
  assert.equal(requests[0].headers['X-CSRF-Token'], 'csrf+current')
  assert.equal(requests[0].credentials, 'include')
  release(mockResponse(internalSession))
  await Promise.all([first, second])
  const third = refreshSession()
  assert.notStrictEqual(third, first)
  assert.equal(requests.length, 2)
  release(mockResponse(internalSession))
  await third
})

test('refresh without CSRF cookie makes no network request', async () => {
  await assert.rejects(refreshSession(), (error) => error instanceof AuthApiError && error.status === 401)
  assert.equal(requests.length, 0)
})

test('cancelling shared refresh aborts the fetch without disturbing a newer shared refresh', async () => {
  document.cookie = 'vietech_csrf=csrf-current'
  const responses = []
  globalThis.fetch = (url, options) => {
    requests.push({ url, ...options })
    const response = deferred()
    options.signal.addEventListener('abort', () => response.reject(options.signal.reason), { once: true })
    responses.push(response)
    return response.promise
  }
  const internal = refreshSession()
  const customer = restoreCustomerSession()
  assert.strictEqual(refreshSession(), internal)
  assert.equal(requests.length, 1)
  const internalAborted = assert.rejects(internal, (error) => error.name === 'AbortError')
  const customerAborted = assert.rejects(customer, (error) => error.name === 'AbortError')
  cancelPendingRefresh()
  assert.equal(requests[0].signal.aborted, true)

  // Start another rotation before the cancelled request's finally callback runs.
  const renewed = refreshSession()
  assert.equal(requests.length, 2)
  assert.equal(requests[1].signal.aborted, false)
  await Promise.all([internalAborted, customerAborted])
  assert.strictEqual(refreshSession(), renewed)
  const nextCustomer = restoreCustomerSession()
  assert.equal(requests.length, 2)
  responses[1].resolve(mockResponse(internalSession))
  assert.deepEqual(await renewed, internalSession)
  assert.equal(await nextCustomer, null)
})

test('a late response from an aborted refresh cannot resolve or clear the newer refresh tracker', async () => {
  document.cookie = 'vietech_csrf=csrf-current'
  const responses = []
  // Simulate a transport double that ignores abort and delivers an old response later.
  globalThis.fetch = (url, options) => {
    requests.push({ url, ...options })
    const response = deferred()
    responses.push(response)
    return response.promise
  }
  const old = refreshSession()
  const oldAborted = assert.rejects(old, (error) => error.name === 'AbortError')
  cancelPendingRefresh()
  const current = refreshSession()
  responses[0].resolve(mockResponse(internalSession))
  await oldAborted
  assert.strictEqual(refreshSession(), current)
  assert.equal(requests.length, 2)
  responses[1].resolve(mockResponse(internalSession))
  assert.equal((await current).user.Role, 'Admin')
})

const rotationCancellingActions = [
  { name: 'internal login', path: '/api/auth/login', role: 'Admin', call: () => loginInternal('admin@example.com', 'Password1!') },
  { name: 'customer login', path: '/api/auth/login', role: 'Customer', call: () => loginCustomer('customer@example.com', 'Password1!') },
  { name: 'logout', path: '/api/auth/logout', role: 'Admin', call: () => logoutSession('access-for-test', 'csrf-for-test') },
]

test.each(rotationCancellingActions)('login and logout cancel old cookie rotations before sending their own requests: $name', async (action) => {
  document.cookie = 'vietech_csrf=csrf-current'
  const events = []
  globalThis.fetch = (url, options) => {
    if (url === '/api/auth/refresh') {
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => {
          events.push('old refresh aborted')
          reject(options.signal.reason)
        }, { once: true })
      })
    }
    events.push(url)
    return Promise.resolve(mockResponse({ ...internalSession, user: { Role: action.role } }))
  }
  const old = refreshSession()
  const oldAborted = assert.rejects(old, (error) => error.name === 'AbortError')
  await action.call()
  await oldAborted
  assert.deepEqual(events, ['old refresh aborted', action.path])
})

test('local logout also aborts an in-flight cookie rotation', async () => {
  document.cookie = 'vietech_csrf=csrf-current'
  globalThis.fetch = (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true })
  })
  const old = refreshSession()
  const oldAborted = assert.rejects(old, (error) => error.name === 'AbortError')
  clearLocalCsrf()
  await oldAborted
  assert.equal(readCsrfToken(), '')
})

test('both Staff and Admin can enter internal login, refresh and current-user views', async () => {
  for (const role of ['Staff', 'Admin']) {
    globalThis.fetch = async () => mockResponse({ ...internalSession, user: { Role: role } })
    assert.equal((await loginInternal('internal@example.com', 'Password1!')).user.Role, role)
    document.cookie = 'vietech_csrf=csrf-current'
    assert.equal((await refreshSession()).user.Role, role)
    assert.equal((await getCurrentUser('access-for-test')).user.Role, role)
  }
})

test('customer and removed roles cannot enter internal login, refresh or current-user views', async () => {
  const denied = (error) => error instanceof AuthApiError && error.status === 403
  for (const role of ['Customer', 'SuperAdmin']) {
    globalThis.fetch = async () => mockResponse({ ...internalSession, user: { Role: role } })
    await assert.rejects(loginInternal('user@example.com', 'Password1!'), denied)
    document.cookie = 'vietech_csrf=csrf-current'
    await assert.rejects(refreshSession(), denied)
    await assert.rejects(getCurrentUser('access-for-test'), denied)
  }
})

test('logout uses bearer access and the latest CSRF cookie', async () => {
  document.cookie = 'vietech_csrf=latest-csrf'
  await logoutSession('access-for-test', 'previous-csrf')
  assert.equal(requests[0].headers.Authorization, 'Bearer access-for-test')
  assert.equal(requests[0].headers['X-CSRF-Token'], 'latest-csrf')
  assert.equal(requests[0].body, undefined)
})

test('local logout expires only the readable CSRF cookie, including Secure over HTTPS', () => {
  document.cookie = 'vietech_csrf=previous-csrf'
  clearLocalCsrf()
  assert.equal(document.cookie, 'vietech_csrf=; Path=/; Max-Age=0; SameSite=Lax')
  assert.equal(readCsrfToken(), '')
  assert.ok(!document.cookie.includes('vietech_refresh'))
  location.protocol = 'https:'
  clearLocalCsrf()
  assert.equal(document.cookie, 'vietech_csrf=; Path=/; Max-Age=0; SameSite=Lax; Secure')
})

test('validation errors are readable in Vietnamese and do not include submitted input', async () => {
  globalThis.fetch = async () => mockResponse({ detail: [{
    loc: ['body', 'Code'], type: 'string_pattern_mismatch',
    msg: 'String should match pattern', input: 'sensitive-for-test',
  }] }, 422)
  await assert.rejects(verifyPasswordReset('challenge-for-test', 'wrong'), (error) => {
    assert.equal(error.status, 422)
    assert.equal(error.message, 'Mã OTP gồm 6 chữ số.')
    assert.ok(!error.message.includes('sensitive-for-test'))
    return true
  })
})

test('offline and rate-limit errors give safe actionable messages', async () => {
  globalThis.fetch = async () => { throw new Error('private transport diagnostics') }
  await assert.rejects(loginInternal('admin@example.com', 'Password1!'), (error) => {
    assert.equal(error.status, 0)
    assert.match(error.message, /Không kết nối được máy chủ/)
    assert.ok(!error.message.includes('private'))
    return true
  })
  globalThis.fetch = async () => mockResponse({ detail: 'Vui lòng thử lại sau 3 phút.' }, 429, { 'Retry-After': '180' })
  await assert.rejects(requestPasswordReset('admin@example.com'), (error) => {
    assert.equal(error.status, 429)
    assert.equal(error.retryAfter, 180)
    assert.equal(error.message, 'Vui lòng thử lại sau 3 phút.')
    return true
  })
})

test('English framework errors are replaced with Vietnamese messages', async () => {
  globalThis.fetch = async () => mockResponse({ detail: 'Not Found' }, 404)
  await assert.rejects(requestPasswordReset('admin@example.com'), (error) => {
    assert.equal(error.message, 'Không tìm thấy chức năng yêu cầu. Vui lòng tải lại trang.')
    return true
  })
  globalThis.fetch = async () => mockResponse({ detail: 'Method Not Allowed' }, 405)
  await assert.rejects(requestPasswordReset('admin@example.com'), (error) => {
    assert.equal(error.message, 'Không thể hoàn tất yêu cầu. Vui lòng thử lại.')
    return true
  })
})

test('customer site restores only customer sessions and shares the rotation', async () => {
  assert.equal(await restoreCustomerSession(), null)
  assert.equal(requests.length, 0)
  document.cookie = 'vietech_csrf=csrf-current'
  globalThis.fetch = async (url, options) => {
    requests.push({ url, ...options })
    return mockResponse({ ...internalSession, user: { Role: 'Customer', FullName: 'Khách' } })
  }
  const [customer, internal] = await Promise.allSettled([restoreCustomerSession(), refreshSession()])
  assert.equal(requests.length, 1)
  assert.equal(customer.value.user.FullName, 'Khách')
  assert.equal(internal.status, 'rejected')
  globalThis.fetch = async () => mockResponse(internalSession)
  assert.equal(await restoreCustomerSession(), null)
  globalThis.fetch = async () => mockResponse({ detail: 'expired' }, 401)
  assert.equal(await restoreCustomerSession(), null)
})

test('customer sign-up posts the exact backend contracts', async () => {
  await registerCustomer({
    FullName: ' Nguyễn Văn A ', Email: ' a@example.com ', PhoneNumber: ' 0912345678 ',
    Password: ' Secret1! ', ConfirmPassword: ' Secret1! ',
  })
  await verifyRegistration('challenge-for-test', ' 123456 ')
  assert.deepEqual(requests.map((entry) => entry.url), ['/api/auth/register', '/api/auth/register/verify'])
  assert.deepEqual(requests.map((entry) => JSON.parse(entry.body)), [
    { FullName: 'Nguyễn Văn A', Email: 'a@example.com', PhoneNumber: '0912345678', Password: ' Secret1! ', ConfirmPassword: ' Secret1! ' },
    { ChallengeId: 'challenge-for-test', Code: '123456' },
  ])
})

test('customer sign-in uses the customer portal and refuses internal accounts', async () => {
  globalThis.fetch = async (url, options) => {
    requests.push({ url, ...options })
    return mockResponse({ ...internalSession, user: { Role: 'Customer', FullName: 'Khách' } })
  }
  assert.equal((await loginCustomer('  khach@example.com ', ' Secret1! ')).user.FullName, 'Khách')
  assert.equal(requests[0].url, '/api/auth/login')
  assert.deepEqual(JSON.parse(requests[0].body), { Identifier: 'khach@example.com', Password: ' Secret1! ', Portal: 'customer' })
  globalThis.fetch = async () => mockResponse(internalSession)
  await assert.rejects(loginCustomer('admin@example.com', 'Secret1!'), (error) => error.status === 403)
})
