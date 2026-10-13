import { useEffect, useState } from 'react'
import AdminLayout from '../layouts/AdminLayout.jsx'
import AccountsPage from './AccountsPage.jsx'
import ProfilePage from './ProfilePage.jsx'

// `permission` hides an entry from roles that cannot use it; the backend still enforces it.
const MENU = [
  { id: 'overview', label: 'Tổng quan' },
  { id: 'accounts', label: 'Quản lý tài khoản', permission: 'users:read' },
]

// Opened from the account button in the top bar, not from the menu.
const PROFILE = { id: 'profile', label: 'Thông tin cá nhân' }

// Each menu section without a page is intentionally empty until its content is defined.
export default function AdminHomePage({ auth }) {
  const menu = MENU.filter((item) => !item.permission || auth.permissions.includes(item.permission))
  const [active, setActive] = useState(MENU[0].id)
  // A page inside a section (e.g. "Thêm tài khoản") extends the breadcrumb.
  const [subPage, setSubPage] = useState(null)
  // Choosing a menu entry again starts that section fresh (e.g. back to the list).
  const [visit, setVisit] = useState(0)
  const current = active === PROFILE.id ? PROFILE : menu.find((item) => item.id === active) ?? menu[0]

  useEffect(() => {
    document.title = `${subPage ?? current.label} | VieTech`
  }, [current, subPage])

  function open(id) {
    setSubPage(null)
    setActive(id)
    setVisit((value) => value + 1)
  }

  return <AdminLayout auth={auth} title={current.label} breadcrumb={`Trang chủ / ${current.label}${subPage ? ` / ${subPage}` : ''}`}
    menu={menu} active={current.id} onSelect={open} onHome={() => open(MENU[0].id)}
    onAccount={() => open(PROFILE.id)} accountActive={current.id === PROFILE.id}>
    {current.id === PROFILE.id && <ProfilePage auth={auth} />}
    {current.id === 'accounts' && <AccountsPage key={visit} auth={auth} onSubPage={setSubPage} />}
  </AdminLayout>
}
