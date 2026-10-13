import { useOutletContext } from 'react-router-dom'
import RequirePermission from '../../auth/RequirePermission.jsx'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import AccountsPage from './AccountsPage.jsx'
import ProfilePage from './ProfilePage.jsx'

// /admin/users: account management for accounts with `users:read` (Admin in the RBAC matrix).
export function AdminUsersSection() {
  const auth = useInternalAuth()
  const { onSubPage, visit } = useOutletContext()
  return <RequirePermission permission="users:read">
    <AccountsPage key={visit} auth={auth} onSubPage={onSubPage} />
  </RequirePermission>
}

// /admin/profile: the signed-in Staff/Admin's own profile.
export function AdminProfileSection() {
  const auth = useInternalAuth()
  return <ProfilePage auth={auth} />
}
