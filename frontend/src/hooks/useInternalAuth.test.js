import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileFunction } from 'node:vm'
import { AuthApiError } from '../lib/auth-api.js'

// Run the production hook's async methods with isolated React/API dependencies.
// Effects are not mounted; state and refs persist across the harness's renders.
const hookSource = readFileSync(new URL('./useInternalAuth.js', import.meta.url), 'utf8')
  .replace(/^import .+\r?\n/gm, '')
  .replace('export default function useInternalAuth()', 'function useInternalAuth()')
const loadHook = compileFunction(`
  const { useCallback, useEffect, useRef, useState, AuthApiError,
    cancelPendingRefresh, clearLocalCsrf, loginInternal, logoutSession, readCsrfToken, refreshSession } = dependencies
  ${hookSource}
  return useInternalAuth
`, ['dependencies'])

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

function harness(api = {}) {
  const states = [], refs = []
  let stateIndex = 0, refIndex = 0, csrfClears = 0
  const renderHook = loadHook({
    useCallback: (callback) => callback,
    useEffect: () => {},
    useRef: (initial) => {
      const index = refIndex++
      if (!(index in refs)) refs[index] = { current: initial }
      return refs[index]
    },
    useState: (initial) => {
      const index = stateIndex++
      if (!(index in states)) states[index] = typeof initial === 'function' ? initial() : initial
      return [states[index], (next) => { states[index] = typeof next === 'function' ? next(states[index]) : next }]
    },
    AuthApiError,
    cancelPendingRefresh: () => {},
    clearLocalCsrf: () => { csrfClears += 1 },
    loginInternal: async () => session(),
    logoutSession: async () => {},
    readCsrfToken: () => '',
    refreshSession: async () => session('renewed'),
    ...api,
  })
  return {
    get current() {
      stateIndex = 0
      refIndex = 0
      return renderHook()
    },
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
  await auth.current.signIn('mock identifier', 'mock password')
  await auth.current.signOut()
  await auth.current.signIn('mock identifier', 'mock password')
  auth.current.endSession()
  assert.deepEqual(events, [
    'cancel refresh', 'login',
    'cancel refresh', 'logout', 'clear local cookies',
    'cancel refresh', 'login',
    'cancel refresh', 'clear local cookies',
  ])
})

test('a pending refresh cannot revive a session ended by logout or password change', async (t) => {
  for (const method of ['signOut', 'endSession']) {
    await t.test(method, async () => {
      const refresh = deferred(), started = deferred()
      const auth = harness({ refreshSession: () => { started.resolve(); return refresh.promise } })
      await auth.current.signIn('mock identifier', 'mock password')
      let calls = 0
      const request = auth.current.withAccessToken(async () => { calls += 1; throw expired() })
      const rejected = assert.rejects(request, (error) => error.status === 401)
      await started.promise
      if (method === 'signOut') await auth.current.signOut()
      else auth.current.endSession('Password changed for test')
      assert.equal(auth.current.user, null)
      refresh.resolve(session('old refresh'))
      await rejected
      assert.equal(auth.current.user, null)
      assert.equal(calls, 1, 'the protected call must not be retried after ending the session')
      assert.equal(auth.csrfClears, 1)
    })
  }
})

test('a refresh from an earlier session cannot replace a newer sign-in', async () => {
  const refresh = deferred(), started = deferred()
  let login = 0, calls = 0
  const auth = harness({
    loginInternal: async () => session(++login === 1 ? 'initial' : 'new sign-in'),
    refreshSession: () => { started.resolve(); return refresh.promise },
  })
  await auth.current.signIn('mock identifier', 'mock password')
  const request = auth.current.withAccessToken(async () => { calls += 1; throw expired() })
  const rejected = assert.rejects(request, (error) => error.status === 401)
  await started.promise
  await auth.current.signIn('mock other identifier', 'mock other password')
  refresh.resolve(session('old refresh'))
  await rejected
  assert.equal(auth.current.user.FullName, 'new sign-in')
  assert.equal(calls, 1)
  assert.equal(auth.csrfClears, 0)
})

test('a rejected refresh from an earlier session cannot clear a newer sign-in', async (t) => {
  for (const status of [401, 403]) {
    await t.test(`HTTP ${status}`, async () => {
      const refresh = deferred(), started = deferred()
      let login = 0
      const auth = harness({
        loginInternal: async () => session(++login === 1 ? 'initial' : 'new sign-in'),
        refreshSession: () => { started.resolve(); return refresh.promise },
      })
      await auth.current.signIn('mock identifier', 'mock password')
      const request = auth.current.withAccessToken(async () => { throw expired() })
      const rejected = assert.rejects(request, (error) => error.status === 401)
      await started.promise
      await auth.current.signIn('mock other identifier', 'mock other password')
      refresh.reject(new AuthApiError('Old refresh rejected for test', status))
      await rejected
      assert.equal(auth.current.user.FullName, 'new sign-in')
      assert.equal(auth.current.error, '')
      assert.equal(auth.csrfClears, 0)
    })
  }
})

test('a late initial 401 does not start refresh after logout', async () => {
  const response = deferred()
  let refreshes = 0
  const auth = harness({ refreshSession: async () => { refreshes += 1; return session('renewed') } })
  await auth.current.signIn('mock identifier', 'mock password')
  const request = auth.current.withAccessToken(() => response.promise)
  const rejected = assert.rejects(request, (error) => error.status === 401)
  await auth.current.signOut()
  response.reject(expired())
  await rejected
  assert.equal(auth.current.user, null)
  assert.equal(refreshes, 0)
})

test('a late successful initial response is discarded after the session ends', async () => {
  const response = deferred()
  const auth = harness()
  await auth.current.signIn('mock identifier', 'mock password')
  const request = auth.current.withAccessToken(() => response.promise)
  const rejected = assert.rejects(request, (error) => error.status === 401)
  auth.current.endSession()
  response.resolve({ FullName: 'old profile response' })
  await rejected
  assert.equal(auth.current.user, null)
})

test('a late successful retry is discarded after logout', async () => {
  const response = deferred(), started = deferred()
  const auth = harness()
  await auth.current.signIn('mock identifier', 'mock password')
  const request = auth.current.withAccessToken(async (token) => {
    if (token === session().access_token) throw expired()
    started.resolve()
    return response.promise
  })
  const rejected = assert.rejects(request, (error) => error.status === 401)
  await started.promise
  await auth.current.signOut()
  response.resolve({ FullName: 'old profile response' })
  await rejected
  assert.equal(auth.current.user, null)
})

test('parallel requests can still refresh and retry in the same session', async () => {
  const refresh = deferred(), started = deferred()
  let refreshes = 0
  const auth = harness({ refreshSession: () => {
    if (++refreshes === 2) started.resolve()
    return refresh.promise
  } })
  await auth.current.signIn('mock identifier', 'mock password')
  const calls = [[], []]
  const requests = calls.map((tokens, index) => auth.current.withAccessToken(async (token) => {
    tokens.push(token)
    if (token === session().access_token) throw expired()
    return `response ${index}`
  }))
  await started.promise
  refresh.resolve(session('renewed'))
  assert.deepEqual(await Promise.all(requests), ['response 0', 'response 1'])
  assert.deepEqual(calls, Array.from({ length: 2 }, () => [session().access_token, session('renewed').access_token]))
  assert.equal(auth.current.user.FullName, 'renewed')
  assert.equal(auth.csrfClears, 0)
})

test('updating the profile does not invalidate a pending request in the same session', async () => {
  const response = deferred()
  const auth = harness()
  await auth.current.signIn('mock identifier', 'mock password')
  const request = auth.current.withAccessToken(() => response.promise)
  auth.current.updateUser({ Role: 'Admin', FullName: 'updated profile' })
  response.resolve('current response')
  assert.equal(await request, 'current response')
  assert.equal(auth.current.user.FullName, 'updated profile')
})

test('a rejected refresh still ends the current expired session', async () => {
  const auth = harness({ refreshSession: async () => { throw expired() } })
  await auth.current.signIn('mock identifier', 'mock password')
  await assert.rejects(auth.current.withAccessToken(async () => { throw expired() }), (error) => error.status === 401)
  assert.equal(auth.current.user, null)
  assert.match(auth.current.error, /hết hạn/)
  assert.equal(auth.csrfClears, 1)
})
