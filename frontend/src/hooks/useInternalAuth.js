import { useCallback, useEffect, useRef, useState } from 'react'
import { AuthApiError, cancelPendingRefresh, clearLocalCsrf, loginInternal, logoutSession, readCsrfToken, refreshSession } from '../lib/auth-api.js'

export default function useInternalAuth() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sessionReady, setSessionReady] = useState(false)
  const [error, setError] = useState('')
  // A success message for the login screen after the session ends on purpose.
  const [notice, setNotice] = useState('')
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
          const restored = await refreshSession()
          if (active && operation.current === current) saveSession(restored)
        }
      } catch (failure) {
        // A missing, expired, or customer session simply shows the login form.
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

  const signIn = useCallback(async (identifier, password) => {
    cancelPendingRefresh()
    const current = ++operation.current
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const next = await loginInternal(identifier, password)
      if (operation.current === current) saveSession(next)
      return next
    } catch (failure) {
      if (operation.current === current) setError(failure.message)
      throw failure
    } finally {
      if (operation.current === current) {
        setSessionReady(true)
        setLoading(false)
      }
    }
  }, [saveSession])

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
          const renewed = await refreshSession()
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
        setSessionReady(true)
        setLoading(false)
      }
    }
  }, [saveSession])

  // Run an authenticated call; an expired access token is refreshed once and retried.
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
      renewed = await refreshSession()
    } catch (failure) {
      requireCurrentSession()
      if ([401, 403].includes(failure.status)) {
        ++operation.current
        clearLocalCsrf()
        saveSession(null)
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
    setError('')
    setNotice(message)
    setSessionReady(true)
    setLoading(false)
  }, [saveSession])

  return {
    user: session?.user ?? null,
    permissions: session?.permissions ?? [],
    accessToken: session?.access_token ?? null,
    loading,
    sessionReady,
    error,
    notice,
    signIn,
    signOut,
    withAccessToken,
    updateUser,
    endSession,
  }
}
