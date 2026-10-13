// AuthProvider with the real auth-api and API client; only fetch is replaced.
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import useCustomerSession from '../hooks/useCustomerSession.js'
import useInternalAuth from '../hooks/useInternalAuth.js'
import { cancelPendingRefresh } from '../lib/auth-api.js'
import { request } from '../services/api/client.js'
import AuthProvider from './AuthProvider.jsx'
import useAuth from './useAuth.js'

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}

function sessionData(role = 'Admin', name = 'initial') {
  return {
    access_token: `${name}-access`, csrf_token: `${name}-csrf`, expires_in: 900, token_type: 'bearer',
    user: { UserId: `${role}-id`, Role: role, FullName: name },
    permissions: role === 'Customer' ? ['customer.portal'] : ['admin.portal', 'users:read'],
  }
}

function setCsrfCookie(value) {
  document.cookie = `vietech_csrf=${value}; Path=/`
}

// Routes fetch calls by URL; /api/auth/refresh answers with `renewed` after an optional gate.
function backend({ login = sessionData(), renewed = sessionData('Admin', 'renewed'), refreshGate, resource } = {}) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async (url, options) => {
    calls.push({ url, ...options })
    if (url === '/api/auth/login') return jsonResponse(login)
    if (url === '/api/auth/refresh') {
      if (refreshGate) await refreshGate
      return typeof renewed === 'function' ? renewed() : jsonResponse(renewed)
    }
    return resource(url, options)
  }))
  return calls
}

const refreshCalls = (calls) => calls.filter((call) => call.url === '/api/auth/refresh')

function renderAuth(options) {
  return renderHook(() => useAuth(), { wrapper: AuthProvider, ...options })
}

beforeEach(() => {
  setCsrfCookie('')
})

afterEach(() => {
  cancelPendingRefresh()
  document.cookie = 'vietech_csrf=; Path=/; Max-Age=0'
  vi.unstubAllGlobals()
})

describe('API calls with the access token', () => {
  test('a 401 renews the session once and retries once with the new token', async () => {
    const calls = backend({
      resource: (_url, options) => (options.headers.Authorization === 'Bearer renewed-access'
        ? jsonResponse({ ok: true })
        : jsonResponse({ detail: 'Phiên đăng nhập không hợp lệ hoặc đã hết hạn.' }, 401)),
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.sessionReady).toBe(true))
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    setCsrfCookie('csrf-1')
    let data
    await act(async () => {
      data = await result.current.withAccessToken((token) => request('/admin/users', { accessToken: token }))
    })
    expect(data).toEqual({ ok: true })
    expect(refreshCalls(calls)).toHaveLength(1)
    expect(refreshCalls(calls)[0].headers['X-CSRF-Token']).toBe('csrf-1')
    expect(calls.filter((call) => call.url === '/api/admin/users').map((call) => call.headers.Authorization))
      .toEqual(['Bearer initial-access', 'Bearer renewed-access'])
    expect(result.current.accessToken).toBe('renewed-access')
  })

  test('a second 401 after the retry is returned without another refresh (no refresh loop)', async () => {
    const calls = backend({ resource: () => jsonResponse({ detail: 'Cần đăng nhập' }, 401) })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.sessionReady).toBe(true))
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    setCsrfCookie('csrf-1')
    let failure
    await act(async () => {
      failure = await result.current.withAccessToken((token) => request('/admin/users', { accessToken: token })).catch((error) => error)
    })
    expect(failure.status).toBe(401)
    expect(refreshCalls(calls)).toHaveLength(1)
    expect(calls.filter((call) => call.url === '/api/admin/users')).toHaveLength(2)
  })

  test('concurrent requests that all receive 401 share a single refresh request', async () => {
    let openGate
    const refreshGate = new Promise((resolve) => { openGate = resolve })
    const calls = backend({
      refreshGate,
      resource: (url, options) => (options.headers.Authorization === 'Bearer renewed-access'
        ? jsonResponse({ url })
        : jsonResponse({ detail: 'Cần đăng nhập' }, 401)),
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.sessionReady).toBe(true))
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    setCsrfCookie('csrf-1')
    const paths = ['/admin/users', '/admin/orders', '/admin/products']
    let responses
    await act(async () => {
      const pending = paths.map((path) => result.current.withAccessToken((token) => request(path, { accessToken: token })))
      await vi.waitFor(() => expect(refreshCalls(calls)).toHaveLength(1))
      openGate()
      responses = await Promise.all(pending)
    })
    expect(responses.map((response) => response.url)).toEqual(paths.map((path) => `/api${path}`))
    expect(refreshCalls(calls)).toHaveLength(1)
  })

  test.each([403, 409, 500])('a %i response is not retried and does not refresh the session', async (status) => {
    const calls = backend({ resource: () => jsonResponse({ detail: 'Lỗi cho test', code: 'test_error' }, status) })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.sessionReady).toBe(true))
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    setCsrfCookie('csrf-1')
    let failure
    await act(async () => {
      failure = await result.current.withAccessToken((token) => request('/orders', { method: 'POST', body: {}, accessToken: token })).catch((error) => error)
    })
    expect(failure).toMatchObject({ status, code: 'test_error' })
    expect(refreshCalls(calls)).toHaveLength(0)
    expect(calls.filter((call) => call.url === '/api/orders')).toHaveLength(1)
    expect(result.current.user.FullName).toBe('initial')
  })

  test('a renewed session of the other portal ends the current session as expired', async () => {
    backend({
      renewed: sessionData('Customer', 'customer elsewhere'),
      resource: () => jsonResponse({ detail: 'Cần đăng nhập' }, 401),
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.sessionReady).toBe(true))
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    setCsrfCookie('csrf-1')
    await act(async () => {
      await result.current.withAccessToken((token) => request('/admin/users', { accessToken: token })).catch(() => {})
    })
    expect(result.current.session).toBeNull()
    expect(result.current.endReason).toBe('expired')
    expect(result.current.error).toMatch(/hết hạn/)
  })
})

describe('session state', () => {
  test('is initializing until the startup restore completes', async () => {
    setCsrfCookie('csrf-1')
    let openGate
    const refreshGate = new Promise((resolve) => { openGate = resolve })
    backend({ refreshGate, renewed: sessionData('Staff', 'Nhân viên') })
    const { result } = renderAuth()
    expect(result.current).toMatchObject({ status: 'initializing', sessionReady: false, session: null })
    await act(async () => { openGate() })
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(result.current).toMatchObject({ isInternal: true, role: 'Staff' })
  })

  test('without a CSRF cookie it is anonymous and makes no request', async () => {
    const calls = backend()
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))
    expect(calls).toHaveLength(0)
  })

  test('an expired startup session is anonymous without an error', async () => {
    setCsrfCookie('csrf-1')
    backend({ renewed: () => jsonResponse({ detail: 'Phiên đăng nhập không hợp lệ hoặc đã hết hạn.' }, 401) })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))
    expect(result.current.error).toBe('')
  })

  test('restores the session once even when StrictMode runs the startup effect twice', async () => {
    setCsrfCookie('csrf-1')
    const calls = backend({ renewed: sessionData('Customer', 'Khách') })
    const { result } = renderAuth({ reactStrictMode: true })
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(refreshCalls(calls)).toHaveLength(1)
    expect(result.current).toMatchObject({ isCustomer: true, isInternal: false, role: 'Customer' })
  })

  test('sign-in keeps tokens in memory only', async () => {
    backend()
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.sessionReady).toBe(true))
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    expect(result.current.accessToken).toBe('initial-access')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  test('sign-out and server-side session end record why the session ended', async () => {
    const calls = backend({ resource: () => jsonResponse({ message: 'Đã đăng xuất' }) })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.sessionReady).toBe(true))
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    await act(() => result.current.signOut())
    expect(result.current).toMatchObject({ session: null, endReason: 'signout', status: 'anonymous' })
    expect(calls.at(-1).url).toBe('/api/auth/logout')
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    expect(result.current.endReason).toBeNull()
    act(() => result.current.endSession('Đã đổi mật khẩu.'))
    expect(result.current).toMatchObject({ session: null, endReason: 'ended', notice: 'Đã đổi mật khẩu.' })
  })

  test('permissions come from the session and are checked as given', async () => {
    backend()
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.sessionReady).toBe(true))
    await act(() => result.current.signInInternal('admin@example.com', 'Password1!'))
    expect(result.current.hasPermission('users:read')).toBe(true)
    expect(result.current.hasPermission('users:manage')).toBe(false)
  })
})

describe('compatibility hooks', () => {
  function renderBoth() {
    return renderHook(() => ({ internal: useInternalAuth(), customer: useCustomerSession() }), { wrapper: AuthProvider })
  }

  test('a Staff session is not a customer; the customer view shows nobody signed in', async () => {
    backend({ login: sessionData('Staff', 'Nhân viên') })
    const { result } = renderBoth()
    await waitFor(() => expect(result.current.customer.ready).toBe(true))
    await act(() => result.current.internal.signIn('staff@example.com', 'Password1!'))
    expect(result.current.internal.user.FullName).toBe('Nhân viên')
    expect(result.current.internal.permissions).toEqual(['admin.portal', 'users:read'])
    expect(result.current.customer.user).toBeNull()
  })

  test('a Customer session is not internal; the internal view shows the login form state', async () => {
    setCsrfCookie('csrf-1')
    backend({ renewed: sessionData('Customer', 'Khách') })
    const { result } = renderBoth()
    await waitFor(() => expect(result.current.customer.user?.FullName).toBe('Khách'))
    expect(result.current.internal).toMatchObject({ user: null, permissions: [], accessToken: null, sessionReady: true })
  })
})
