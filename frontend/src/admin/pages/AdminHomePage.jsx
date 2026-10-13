import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import AdminLayout from '../layouts/AdminLayout.jsx'
import { ADMIN_MENU, ADMIN_PROFILE_ITEM, visibleMenu } from '../routes/menu.js'

// Internal area frame (layout route for /admin, /admin/users, /admin/profile). Sections render in the <Outlet />;
// "Tổng quan" is intentionally empty until its content is defined.
export default function AdminHomePage() {
  const auth = useInternalAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const path = pathname.replace(/\/+$/, '') || '/'
  const menu = visibleMenu(auth.permissions)
  const current = path === ADMIN_PROFILE_ITEM.path ? ADMIN_PROFILE_ITEM : ADMIN_MENU.find((item) => item.path === path) ?? ADMIN_MENU[0]
  // A page inside a section (e.g. "Thêm tài khoản") extends the breadcrumb; it belongs to the URL it was set on.
  const [subPage, setSubPage] = useState(null)
  // Choosing a menu entry again starts that section fresh (e.g. back to the list).
  const [visit, setVisit] = useState(0)
  const subPageLabel = subPage?.path === path ? subPage.label : null
  const onSubPage = useCallback((label) => setSubPage(label ? { path, label } : null), [path])

  useEffect(() => {
    document.title = `${subPageLabel ?? current.label} | VieTech`
  }, [current, subPageLabel])

  function open(item) {
    setSubPage(null)
    setVisit((value) => value + 1)
    navigate(item.path)
  }

  return <AdminLayout auth={auth} title={current.label} breadcrumb={`Trang chủ / ${current.label}${subPageLabel ? ` / ${subPageLabel}` : ''}`}
    menu={menu} active={current.id} onSelect={(id) => open(menu.find((item) => item.id === id))} onHome={() => open(ADMIN_MENU[0])}
    onAccount={() => open(ADMIN_PROFILE_ITEM)} accountActive={current.id === ADMIN_PROFILE_ITEM.id}>
    <Outlet context={{ onSubPage, visit }} />
  </AdminLayout>
}
