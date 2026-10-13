import useAuth from '../auth/useAuth.js'

// Customer site view of the shared session. `ready` is false until the startup restore finishes, so the header
// does not flash "Đăng nhập" for a customer who is already signed in. A Staff/Admin session counts as no customer.
// Kept for the existing customer pages; the logic lives in AuthProvider.
export default function useCustomerSession() {
  const auth = useAuth()
  return {
    ready: auth.sessionReady,
    user: auth.isCustomer ? auth.user : null,
    withAccessToken: auth.withAccessToken,
    updateUser: auth.updateUser,
    endSession: auth.endSession,
    signOut: auth.signOut,
  }
}
