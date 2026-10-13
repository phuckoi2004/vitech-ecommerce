import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { buttonClassName } from '../components/shared/buttonStyles.js'
import EmptyState from '../components/shared/EmptyState.jsx'
import LoadingState from '../components/shared/LoadingState.jsx'
import { ACCOUNT_PATH, HOME_PATH, LOGIN_PATH } from '../customer/routes/paths.js'
import { nextQuery } from './session.js'
import useAuth from './useAuth.js'

// Customer-only page. This only decides what the browser shows; the backend checks every request itself.
// - no session: sign in, then come back here (`?next=`);
// - Staff/Admin session: a notice with a link to the internal area, without signing them out;
// - the customer's own session ended here: sign-out goes home, a server-side end (password change) to the sign-in
//   page with its "password changed" notice (the customer site only ends sessions for that reason).
export default function RequireCustomer({ children }) {
  const auth = useAuth()
  const location = useLocation()
  // Whether this page was showing a customer session, so its end is not mistaken for a first visit.
  const [hadCustomer, setHadCustomer] = useState(auth.isCustomer)
  if (auth.isCustomer && !hadCustomer) setHadCustomer(true)

  if (!auth.sessionReady) return <LoadingState label="Đang tải thông tin tài khoản…" />
  if (auth.isCustomer) return children
  if (auth.session) {
    return <EmptyState title="Bạn đang đăng nhập bằng tài khoản nội bộ"
      description={location.pathname === ACCOUNT_PATH
        ? 'Trang tài khoản chỉ dành cho khách hàng. Tài khoản nhân viên và quản trị viên được quản lý trong khu vực quản trị.'
        : 'Trang này chỉ dành cho khách hàng. Tài khoản nhân viên và quản trị viên làm việc trong khu vực quản trị.'}
      action={<Link className={buttonClassName()} to="/admin">Đến khu vực quản trị</Link>} />
  }
  if (hadCustomer && auth.endReason === 'signout') return <Navigate to={HOME_PATH} replace />
  if (hadCustomer && auth.endReason === 'ended') return <Navigate to={`${LOGIN_PATH}?doi-mat-khau=1`} replace />
  return <Navigate to={`${LOGIN_PATH}${nextQuery(location)}`} replace />
}
