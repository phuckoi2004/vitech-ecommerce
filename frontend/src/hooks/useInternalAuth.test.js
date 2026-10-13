// Converted from the node:test + vm harness (which compiled useInternalAuth.js with stubbed React hooks) to
// React Testing Library: the hook now runs inside the real AuthProvider with React's own hooks.
// Every scenario and assertion is kept; the session API module is mocked instead of injected.
// The old harness option `refreshSession` is now `renewSession`: the provider renews any portal's session.
import assert from 'node:assert/strict'
import { act, renderHook } from '@testing-library/react'
import { test, vi } from 'vitest'
import AuthProvider from '../auth/AuthProvider.jsx'
import { AuthApiError } from '../lib/auth-api.js'
import useInternalAuth from './useInternalAuth.js'

const api = vi.hoisted(() => ({ current: {} }))

vi.mock('../lib/auth-api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const call = (name) => (...args) => api.current[name](...args)
  return {
    ...actual,
    cancelPendingRefresh: call('cancelPendingRefresh'),
    clearLocalCsrf: call('clearLocalCsrf'),
    loginCustomer: call('loginCustomer'),
    loginInternal: call('loginInternal'),
    logoutSession: call('logoutSession'),
    readCsrfToken: call('readCsrfToken'),
    renewSession: call('renewSession'),
  }
})

function deferred() {
  let resolve, reject
  const promise = new Promise((accept, decline) => { resolve = accept; reject = decline })
  return { promise, resolve, reject }
}

function session(name = 'initial') {
  return {
    access_token: `${name}-access-for-test`, csrf_token: `${name}-csrf-for-test`,
    user: { Role: 'Admin', FullName: name }, permissions: ['users:read', 'users:manage'],
  }
}

function harness(overrides = {}) {
  let csrfClears = 0
  api.current = {
    cancelPendingRefresh: () => {},
    clearLocalCsrf: () => { csrfClears += 1 },
    loginCustomer: async () => session(),
    loginInternal: async () => session(),
    logoutSession: async () => {},
    // No CSRF cookie: the provider starts signed out without a startup refresh.
    readCsrfToken: () => '',
    renewSession: async () => session('renewed'),
    ...overrides,
  }
  const { result } = renderHook(() => useInternalAuth(), { wrapper: AuthProvider })
  return {
    get current() { return result.current },
    get csrfClears() { return csrfClears },
  }
}

function expired() {
  return new AuthApiError('Expired access token for test', 401)
}

test('session-changing operations cancel refresh before starting or clearing authentication', async () => {
  const events = []
  const auth = harness({
    cancelPendingRefresh: () => { events.push('cancel refresh') },
    clearLocalCsrf: () => { events.push('clear local cookies') },
    loginInternal: async () => { events.push('login'); return session() },
    logoutSession: async () => { events.push('logout') },
  })
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  await act(() => auth.current.signOut())
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  act(() => auth.current.endSession())
  assert.deepEqual(events, [
    'cancel refresh', 'login',
    'cancel refresh', 'logout', 'clear local cookies',
    'cancel refresh', 'login',
    'cancel refresh', 'clear local cookies',
  ])
})

test.each(['signOut', 'endSession'])('a pending refresh cannot revive a session ended by logout or password change: %s', async (method) => {
  const refresh = deferred(), started = deferred()
  const auth = harness({ renewSession: () => { started.resolve(); return refresh.promise } })
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  let calls = 0
  const request = auth.current.withAccessToken(async () => { calls += 1; throw expired() })
  const rejected = assert.rejects(request, (error) => error.status === 401)
  await act(() => started.promise)
  if (method === 'signOut') await act(() => auth.current.signOut())
  else act(() => auth.current.endSession('Password changed for test'))
  assert.equal(auth.current.user, null)
  await act(async () => {
    refresh.resolve(session('old refresh'))
    await rejected
  })
  assert.equal(auth.current.user, null)
  assert.equal(calls, 1, 'the protected call must not be retried after ending the session')
  assert.equal(auth.csrfClears, 1)
})

test('a refresh from an earlier session cannot replace a newer sign-in', async () => {
  const refresh = deferred(), started = deferred()
  let login = 0, calls = 0
  const auth = harness({
    loginInternal: async () => session(++login === 1 ? 'initial' : 'new sign-in'),
    renewSession: () => { started.resolve(); return refresh.promise },
  })
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  const request = auth.current.withAccessToken(async () => { calls += 1; throw expired() })
  const rejected = assert.rejects(request, (error) => error.status === 401)
  await act(() => started.promise)
  await act(() => auth.current.signIn('mock other identifier', 'mock other password'))
  await act(async () => {
    refresh.resolve(session('old refresh'))
    await rejected
  })
  assert.equal(auth.current.user.FullName, 'new sign-in')
  assert.equal(calls, 1)
  assert.equal(auth.csrfClears, 0)
})

test.each([401, 403])('a rejected refresh from an earlier session cannot clear a newer sign-in: HTTP %i', async (status) => {
  const refresh = deferred(), started = deferred()
  let login = 0
  const auth = harness({
    loginInternal: async () => session(++login === 1 ? 'initial' : 'new sign-in'),
    renewSession: () => { started.resolve(); return refresh.promise },
  })
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  const request = auth.current.withAccessToken(async () => { throw expired() })
  const rejected = assert.rejects(request, (error) => error.status === 401)
  await act(() => started.promise)
  await act(() => auth.current.signIn('mock other identifier', 'mock other password'))
  await act(async () => {
    refresh.reject(new AuthApiError('Old refresh rejected for test', status))
    await rejected
  })
  assert.equal(auth.current.user.FullName, 'new sign-in')
  assert.equal(auth.current.error, '')
  assert.equal(auth.csrfClears, 0)
})

test('a late initial 401 does not start refresh after logout', async () => {
  const response = deferred()
  let refreshes = 0
  const auth = harness({ renewSession: async () => { refreshes += 1; return session('renewed') } })
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  const request = auth.current.withAccessToken(() => response.promise)
  const rejected = assert.rejects(request, (error) => error.status === 401)
  await act(() => auth.current.signOut())
  await act(async () => {
    response.reject(expired())
    await rejected
  })
  assert.equal(auth.current.user, null)
  assert.equal(refreshes, 0)
})

test('a late successful initial response is discarded after the session ends', async () => {
  const response = deferred()
  const auth = harness()
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  const request = auth.current.withAccessToken(() => response.promise)
  const rejected = assert.rejects(request, (error) => error.status === 401)
  act(() => auth.current.endSession())
  await act(async () => {
    response.resolve({ FullName: 'old profile response' })
    await rejected
  })
  assert.equal(auth.current.user, null)
})

test('a late successful retry is discarded after logout', async () => {
  const response = deferred(), started = deferred()
  const auth = harness()
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  const request = auth.current.withAccessToken(async (token) => {
    if (token === session().access_token) throw expired()
    started.resolve()
    return response.promise
  })
  const rejected = assert.rejects(request, (error) => error.status === 401)
  await act(() => started.promise)
  await act(() => auth.current.signOut())
  await act(async () => {
    response.resolve({ FullName: 'old profile response' })
    await rejected
  })
  assert.equal(auth.current.user, null)
})

test('parallel requests can still refresh and retry in the same session', async () => {
  const refresh = deferred(), started = deferred()
  let refreshes = 0
  const auth = harness({ renewSession: () => {
    if (++refreshes === 2) started.resolve()
    return refresh.promise
  } })
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  const calls = [[], []]
  const requests = calls.map((tokens, index) => auth.current.withAccessToken(async (token) => {
    tokens.push(token)
    if (token === session().access_token) throw expired()
    return `response ${index}`
  }))
  await act(() => started.promise)
  let responses
  await act(async () => {
    refresh.resolve(session('renewed'))
    responses = await Promise.all(requests)
  })
  assert.deepEqual(responses, ['response 0', 'response 1'])
  assert.deepEqual(calls, Array.from({ length: 2 }, () => [session().access_token, session('renewed').access_token]))
  assert.equal(auth.current.user.FullName, 'renewed')
  assert.equal(auth.csrfClears, 0)
})

test('updating the profile does not invalidate a pending request in the same session', async () => {
  const response = deferred()
  const auth = harness()
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  const request = auth.current.withAccessToken(() => response.promise)
  act(() => auth.current.updateUser({ Role: 'Admin', FullName: 'updated profile' }))
  let value
  await act(async () => {
    response.resolve('current response')
    value = await request
  })
  assert.equal(value, 'current response')
  assert.equal(auth.current.user.FullName, 'updated profile')
})

test('a rejected refresh still ends the current expired session', async () => {
  const auth = harness({ renewSession: async () => { throw expired() } })
  await act(() => auth.current.signIn('mock identifier', 'mock password'))
  await act(() => assert.rejects(auth.current.withAccessToken(async () => { throw expired() }), (error) => error.status === 401))
  assert.equal(auth.current.user, null)
  assert.match(auth.current.error, /hết hạn/)
  assert.equal(auth.csrfClears, 1)
})
