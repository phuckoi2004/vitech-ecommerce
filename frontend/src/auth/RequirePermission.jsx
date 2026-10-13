import ErrorState from '../components/shared/ErrorState.jsx'
import useAuth from './useAuth.js'

// Hides a section from accounts whose session lacks `permission` (codes from the backend RBAC matrix).
// Direct links show a message instead of the section; the backend refuses the requests anyway.
export default function RequirePermission({ permission, children }) {
  const { permissions } = useAuth()
  if (!permissions.includes(permission)) {
    return <ErrorState title="Không có quyền truy cập" message="Tài khoản của bạn không có quyền sử dụng chức năng này." />
  }
  return children
}
