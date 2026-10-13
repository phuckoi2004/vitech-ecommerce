import { useContext } from 'react'
import { AuthContext } from './context.js'

// The shared session: user, role helpers, permissions from /auth/me or login, and the session operations.
export default function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside <AuthProvider>.')
  return auth
}
