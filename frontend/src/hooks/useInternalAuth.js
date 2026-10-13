import useAuth from '../auth/useAuth.js'

// Internal area view of the shared session (Staff/Admin). A Customer session in this browser counts as signed out
// here, so the internal login form is shown. Kept for the existing admin pages; the logic lives in AuthProvider.
export default function useInternalAuth() {
  const auth = useAuth()
  const user = auth.isInternal ? auth.user : null
  return {
    user,
    permissions: user ? auth.permissions : [],
    accessToken: user ? auth.accessToken : null,
    loading: auth.loading,
    sessionReady: auth.sessionReady,
    error: auth.error,
    notice: auth.notice,
    signIn: auth.signInInternal,
    signOut: auth.signOut,
    withAccessToken: auth.withAccessToken,
    updateUser: auth.updateUser,
    endSession: auth.endSession,
  }
}
