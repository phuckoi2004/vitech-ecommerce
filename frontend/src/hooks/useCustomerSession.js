import { useCallback, useEffect, useRef, useState } from 'react'
import { AuthApiError, cancelPendingRefresh, clearLocalCsrf, logoutSession, restoreCustomerSession } from '../lib/auth-api.js'

// Several components hold their own copy of the session (header, account page); a saved profile
// is announced so every copy shows the same name and avatar.
const USER_UPDATED = 'vietech:customer-user-updated'

// The signed-in customer, from the refresh cookie. `ready` is false until the check finishes,
// so the header does not flash "Đăng nhập" for a customer who is already signed in.
export default function useCustomerSession() {
  const [state, setState] = useState({ ready: false, session: null })
  const sessionRef = useRef(null)

  const saveSession = useCallback((session) => {
    sessionRef.current = session
    setState({ ready: true, session })
  }, [])

  useEffect(() => {
    let active = true
    restoreCustomerSession()
      .catch(() => null)
      .then((session) => { if (active) saveSession(session) })
    return () => { active = false }
  }, [saveSession])

  // Runs an API call with the access token, renewing the session once if the token has expired.
  const withAccessToken = useCallback(async (call) => {
    const existing = sessionRef.current
    if (!existing) throw new AuthApiError('Vui lòng đăng nhập để tiếp tục.', 401)
    try {
      return await call(existing.access_token)
    } catch (failure) {
      if (failure.status !== 401) throw failure
    }
    const renewed = await restoreCustomerSession()
    saveSession(renewed)
    if (!renewed) throw new AuthApiError('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', 401)
    return call(renewed.access_token)
  }, [saveSession])

  useEffect(() => {
    function applyUpdate(event) {
      const existing = sessionRef.current
      if (existing?.user?.UserId === event.detail.UserId) saveSession({ ...existing, user: event.detail })
    }
    window.addEventListener(USER_UPDATED, applyUpdate)
    return () => window.removeEventListener(USER_UPDATED, applyUpdate)
  }, [saveSession])

  // Every copy, this one included, picks the new user up through the event.
  const updateUser = useCallback((user) => {
    window.dispatchEvent(new CustomEvent(USER_UPDATED, { detail: user }))
  }, [])

  // Forget the session in this browser, e.g. after a password change the server already revoked it.
  const endSession = useCallback(() => {
    cancelPendingRefresh()
    clearLocalCsrf()
    saveSession(null)
  }, [saveSession])

  // Revokes the session on the server, then forgets it locally even if the server could not be reached.
  const signOut = useCallback(async () => {
    const existing = sessionRef.current
    try {
      if (!existing) return
      try {
        await logoutSession(existing.access_token, existing.csrf_token)
      } catch (failure) {
        if (failure.status !== 401) throw failure
        // An expired access token still needs server-side session revocation.
        const renewed = await restoreCustomerSession()
        if (renewed) await logoutSession(renewed.access_token, renewed.csrf_token)
      }
    } finally {
      endSession()
    }
  }, [endSession])

  return { ready: state.ready, user: state.session?.user ?? null, withAccessToken, updateUser, endSession, signOut }
}
