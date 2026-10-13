import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ADMIN_LOGIN_PATH } from '../admin/routes/paths.js'
import LoadingState from '../components/shared/LoadingState.jsx'
import { nextQuery } from './session.js'
import useAuth from './useAuth.js'

// Staff/Admin-only area. Without an internal session (signed out, or a Customer session in this browser) the internal
// login form is shown and returns here afterwards (`?next=`). After an intentional sign-out or a server-side end
// (password change) the login page opens without `next`, as before. The backend still checks every request.
export default function RequireInternal({ children }) {
  const auth = useAuth()
  const location = useLocation()
  // Whether this area was showing an internal session, so its end is not mistaken for a first visit.
  const [hadInternal, setHadInternal] = useState(auth.isInternal)
  if (auth.isInternal && !hadInternal) setHadInternal(true)

  if (!auth.sessionReady) return <LoadingState fullScreen label="Đang mở không gian làm việc…" />
  if (auth.isInternal) return children
  const ended = hadInternal && ['signout', 'ended'].includes(auth.endReason)
  return <Navigate to={ended ? ADMIN_LOGIN_PATH : `${ADMIN_LOGIN_PATH}${nextQuery(location)}`} replace />
}
