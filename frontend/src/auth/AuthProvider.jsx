import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AuthApiError, cancelPendingRefresh, clearLocalCsrf, loginCustomer, loginInternal, logoutSession, readCsrfToken,
  renewSession,
} from '../lib/auth-api.js'
import { AuthContext } from './context.js'
import { sessionArea } from './session.js'

// One session for the whole app. The browser holds a single refresh cookie shared by the customer site and the
// internal area, so this state is either a Customer session, a Staff/Admin session, or none. Pages decide what a
// session of the other portal means for them (see the route guards).
//
// The access token, CSRF token and user stay in memory only; the HttpOnly refresh cookie restores them after a reload.
// `operation` increases whenever the session starts, ends or is replaced, so late responses of an older session
// can never revive or clear the current one.
export default function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  // True while the startup restore, a sign-in or a sign-out is running.
  const [loading, setLoading] = useState(true)
  const [sessionReady, setSessionReady] = useState(false)
  const [error, setError] = useState('')
  // A success message for the sign-in screen after the session ends on purpose.
  const [notice, setNotice] = useState('')
  // Why the last session ended: 'signout', 'ended' (revoked by the server, e.g. password change) or 'expired'.
  const [endReason, setEndReason] = useState(null)
  const sessionRef = useRef(null)
  const operation = useRef(0)

  const saveSession = useCallback((next) => {
    sessionRef.current = next
    setSession(next)
  }, [])

  useEffect(() => {
    const current = ++operation.current
    let active = true

    async function restore() {
      try {
        if (readCsrfToken()) {
          // Shares the cookie rotation with any other caller (StrictMode runs this effect twice).
          const restored = await renewSession()
          if (active && operation.current === current) saveSession(restored)
        }
      } catch (failure) {
        // A missing, expired or unsupported session simply means nobody is signed in.
        if (active && operation.current === current && ![401, 403].includes(failure.status)) {
          setError(failure.message)
        }
      } finally {
        if (active && operation.current === current) {
          setSessionReady(true)
          setLoading(false)
        }
      }
    }

    restore()
    return () => {
      active = false
      operation.current += 1
    }
  }, [saveSession])

  const startSession = useCallback(async (login, identifier, password, { reportError }) => {
    cancelPendingRefresh()
    const current = ++operation.current
    setLoading(true)
    if (reportError) setError('')
    setNotice('')
    try {
      const next = await login(identifier, password)
      if (operation.current === current) {
        saveSession(next)
        setEndReason(null)
        setError('')
      }
      return next
    } catch (failure) {
      if (reportError && operation.current === current) setError(failure.message)
      throw failure
    } finally {
      if (operation.current === current) {
        setSessionReady(true)
        setLoading(false)
      }
    }
  }, [saveSession])

  // Internal sign-in reports its error to the shared state (the internal login form shows it).
  const signInInternal = useCallback((identifier, password) => (
    startSession(loginInternal, identifier, password, { reportError: true })
  ), [startSession])

  // Customer sign-in: the login page shows its own error message.
  const signInCustomer = useCallback((identifier, password) => (
    startSession(loginCustomer, identifier, password, { reportError: false })
  ), [startSession])

  const signOut = useCallback(async () => {
    cancelPendingRefresh()
    const current = ++operation.current
    const existing = sessionRef.current
    setLoading(true)
    setError('')
    try {
      if (existing) {
        try {
          await logoutSession(existing.access_token, existing.csrf_token)
        } catch (failure) {
          if (failure.status !== 401) throw failure
          // An expired access token still needs server-side session revocation.
          const renewed = await renewSession()
          await logoutSession(renewed.access_token, renewed.csrf_token)
        }
      }
    } catch (failure) {
      if (operation.current === current && failure.status !== 401) {
        setError('Đã đăng xuất trên thiết bị này. Chưa thể kết thúc phiên trên máy chủ, vui lòng kiểm tra kết nối.')
        throw failure
      }
    } finally {
      if (operation.current === current) {
        clearLocalCsrf()
        saveSession(null)
        setEndReason('signout')
        setSessionReady(true)
        setLoading(false)
      }
    }
  }, [saveSession])

  // Runs an authenticated call. On 401 the session is renewed once (overlapping renewals share one cookie
  // rotation) and the call is retried once with the new token. A 401 is answered before the backend runs the
  // use case, so the single retry is safe for writes as well. Other errors are never retried.
  const withAccessToken = useCallback(async (call) => {
    const existing = sessionRef.current
    if (!existing) throw new AuthApiError('Vui lòng đăng nhập để tiếp tục.', 401)
    const current = operation.current
    function requireCurrentSession() {
      if (operation.current !== current || !sessionRef.current) {
        throw new AuthApiError('Phiên đăng nhập đã thay đổi. Vui lòng thử lại.', 401)
      }
    }
    async function invoke(token) {
      try {
        return await call(token)
      } finally {
        // Discard a response from a session ended or replaced while awaiting it.
        requireCurrentSession()
      }
    }
    try {
      return await invoke(existing.access_token)
    } catch (failure) {
      requireCurrentSession()
      if (failure.status !== 401) throw failure
    }
    let renewed
    try {
      renewed = await renewSession()
      // The cookie now belongs to the other portal (signed in elsewhere in this browser).
      if (sessionArea(renewed) !== sessionArea(existing)) {
        throw new AuthApiError('Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.', 403)
      }
    } catch (failure) {
      requireCurrentSession()
      if ([401, 403].includes(failure.status)) {
        ++operation.current
        clearLocalCsrf()
        saveSession(null)
        setEndReason('expired')
        setError('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
      }
      throw failure
    }
    requireCurrentSession()
    saveSession(renewed)
    return invoke(renewed.access_token)
  }, [saveSession])

  const updateUser = useCallback((user) => {
    if (sessionRef.current) saveSession({ ...sessionRef.current, user })
  }, [saveSession])

  // The server already revoked every session (e.g. password change); only local state remains.
  const endSession = useCallback((message = '') => {
    cancelPendingRefresh()
    ++operation.current
    clearLocalCsrf()
    saveSession(null)
    setEndReason('ended')
    setError('')
    setNotice(message)
    setSessionReady(true)
    setLoading(false)
  }, [saveSession])

  const value = useMemo(() => {
    const area = sessionArea(session)
    const permissions = session?.permissions ?? []
    let status = 'anonymous'
    if (!sessionReady) status = 'initializing'
    else if (loading) status = 'authenticating'
    else if (session) status = 'authenticated'
    return {
      status,
      session,
      user: session?.user ?? null,
      role: session?.user?.Role ?? null,
      area,
      isCustomer: area === 'customer',
      isInternal: area === 'internal',
      permissions,
      accessToken: session?.access_token ?? null,
      hasPermission: (permission) => permissions.includes(permission),
      loading,
      sessionReady,
      error,
      notice,
      endReason,
      signInInternal,
      signInCustomer,
      signOut,
      withAccessToken,
      updateUser,
      endSession,
    }
  }, [session, loading, sessionReady, error, notice, endReason, signInInternal, signInCustomer, signOut,
    withAccessToken, updateUser, endSession])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
