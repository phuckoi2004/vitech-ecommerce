import { useEffect, useState } from 'react'
import AdminLayout from '../layouts/AdminLayout.jsx'
import { allowedMenu, PROFILE, sectionFromPath, sectionPath } from '../routes.js'
import AccountsPage from './AccountsPage.jsx'
import DashboardPage from './DashboardPage.jsx'
import SectionPage from './SectionPage.jsx'
import ProfilePage from './ProfilePage.jsx'

export default function AdminHomePage({ auth }) {
  const menu = allowedMenu(auth.permissions)
  const sections = menu.flatMap((item) => item.children ?? item)
  const [active, setActive] = useState(() => sectionFromPath(window.location.pathname))
  // A page inside a section (e.g. "Thêm tài khoản") extends the breadcrumb.
  const [subPage, setSubPage] = useState(null)
  // Choosing a menu entry again starts that section fresh (e.g. back to the list).
  const [visit, setVisit] = useState(0)
  const current = active === PROFILE.id ? PROFILE : sections.find((item) => item.id === active) ?? sections[0]

  useEffect(() => {
    document.title = `${subPage ?? current.label} | VieTech`
  }, [current.label, subPage])

  useEffect(() => {
    function pop() {
      setActive(sectionFromPath(window.location.pathname))
      setSubPage(null)
      setVisit((value) => value + 1)
    }
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])

  useEffect(() => {
    const path = sectionPath(current.id)
    if (window.location.pathname !== path) window.history.replaceState(null, '', path)
  }, [current.id, active])

  function open(id) {
    if (id !== PROFILE.id && !sections.some((item) => item.id === id)) return
    setSubPage(null)
    setActive(id)
    setVisit((value) => value + 1)
    const path = sectionPath(id)
    if (window.location.pathname !== path) window.history.pushState(null, '', path)
  }

  return <AdminLayout auth={auth} title={current.id === 'overview' ? 'Dashboard' : current.label} breadcrumb={`Trang chủ / ${current.label}${subPage ? ` / ${subPage}` : ''}`}
    menu={menu} active={current.id} onSelect={open} onHome={() => open('overview')}
    onAccount={() => open(PROFILE.id)} accountActive={current.id === PROFILE.id}>
    {current.id === 'overview' && <DashboardPage key={visit} auth={auth} onSelect={open} />}
    {current.id === PROFILE.id && <ProfilePage auth={auth} />}
    {current.id === 'accounts' && <AccountsPage key={visit} auth={auth} onSubPage={setSubPage} />}
    {!['overview', 'profile', 'accounts'].includes(current.id) && <SectionPage key={`${current.id}-${visit}`} section={current} auth={auth} />}
  </AdminLayout>
}
