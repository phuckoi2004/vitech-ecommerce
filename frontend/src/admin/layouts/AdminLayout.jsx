import { useState } from 'react'
import Icon from '../components/Icon.jsx'
import AdminNotifications from '../components/AdminNotifications.jsx'
import './AdminLayout.css'

const ROLES = { Staff: 'Nhân viên', Admin: 'Quản trị viên' }

function initials(name = '') {
  const words = name.trim().split(/\s+/).filter(Boolean)
  return (words.length > 1 ? words[0][0] + words.at(-1)[0] : words[0]?.[0] ?? '?').toUpperCase()
}

export function Avatar({ user, className = '' }) {
  // Keep the admin-avatar marker for the existing profile page's larger avatar.
  const avatarClass = `admin-avatar inline-grid size-[38px] shrink-0 place-items-center rounded-full text-[13px] font-bold text-white ${className}`
  return user.AvatarUrl
    ? <img className={`${avatarClass} bg-admin-soft object-cover`} src={user.AvatarUrl} alt="" />
    : <span className={`${avatarClass} bg-admin-navy`} aria-hidden="true">{initials(user.FullName)}</span>
}

// "Trang chủ / A / B": the first segment links back to the home section.
function Breadcrumb({ trail, onHome }) {
  const [home, ...rest] = trail.split(' / ')
  return <p className="mt-0.5 text-xs leading-normal text-admin-muted">
    <button type="button" className="cursor-pointer rounded-[3px] border-0 bg-transparent p-0 text-inherit hover:text-admin-blue hover:underline" onClick={onHome}>{home}</button>
    {rest.map((part) => <span key={part}> / {part}</span>)}
  </p>
}

export default function AdminLayout({ auth, title, breadcrumb, menu = [], active, onSelect, onHome, onBreadcrumbHome, onAccount, accountActive = false, sidebarLogo, children }) {
  const { user } = auth
  const role = ROLES[user.Role] ?? user.Role
  const [expanded, setExpanded] = useState(null)
  const [collapsed, setCollapsed] = useState(null)

  function navItem(item, nested = false) {
    const isActive = item.id === active || item.children?.some((child) => child.id === active)
    const isOpen = expanded === item.id || (isActive && collapsed !== item.id)
    return <div key={item.id} className="min-w-0 shrink-0">
      <button type="button" className={`relative flex w-full shrink-0 cursor-pointer items-center gap-2 rounded-[10px] border-0 py-2.5 pr-3 text-left leading-normal font-medium text-white transition-colors duration-150 max-[860px]:pr-3.5 max-[860px]:whitespace-nowrap ${nested ? 'min-h-[38px] pl-4 text-xs' : 'min-h-11 pl-[26px] text-sm'} ${isActive ? 'bg-admin-blue' : 'bg-transparent hover:bg-white/8'}`} aria-current={item.id === active ? 'page' : undefined}
        aria-expanded={item.children ? isOpen : undefined} aria-controls={item.children ? `admin-menu-${item.id}` : undefined}
        onClick={() => {
          if (!item.children) return onSelect(item.id)
          setExpanded(isOpen ? null : item.id)
          setCollapsed(isOpen ? item.id : null)
        }}>
        {isActive && <span className="absolute inset-y-2.5 left-3 w-1 rounded-sm bg-admin-red" aria-hidden="true" />}
        <span>{item.label}</span>{item.children && <span className="ml-auto text-[11px] text-admin-soft" aria-hidden="true">{isOpen ? '▲' : '▼'}</span>}
      </button>
      {item.children && isOpen && <div className="mt-1.5 flex flex-col gap-1 pl-4 max-[860px]:pl-0" id={`admin-menu-${item.id}`}>{item.children.map((child) => navItem(child, true))}</div>}
    </div>
  }

  async function signOut() {
    try { await auth.signOut() } catch { /* The hook displays a connection error on the login screen. */ }
  }

  return <div className="admin-shell flex min-h-dvh bg-admin-page font-admin text-admin-text antialiased max-[860px]:flex-col **:focus-visible:outline-2! **:focus-visible:outline-solid! **:focus-visible:outline-admin-blue! **:focus-visible:outline-offset-3!">
    <aside className="admin-sidebar sticky top-0 flex h-dvh w-[248px] shrink-0 flex-col bg-admin-navy px-5 pt-7 pb-6 text-white max-[860px]:static max-[860px]:h-auto max-[860px]:w-full max-[860px]:px-4 max-[860px]:pt-3.5 max-[860px]:pb-3" aria-label="Thanh điều hướng quản trị">
      <button type="button" className="flex cursor-pointer flex-col gap-0.5 rounded-md border-0 bg-transparent px-2 text-left text-inherit" onClick={onHome} title="Về trang chủ">{sidebarLogo && <img src={sidebarLogo} alt="" width="93" height="57" className="h-[57px] w-[93px] shrink-0 object-cover" />}<strong className="text-2xl leading-[1.2] font-bold max-[860px]:text-[18px]">VIETECH</strong><span className="text-[10px] font-semibold text-admin-soft">ADMIN PANEL</span></button>
      <nav className="mt-[26px] flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto [scrollbar-color:#60708a_transparent] [scrollbar-width:thin] max-[860px]:mt-3 max-[860px]:max-h-[220px] max-[860px]:flex-row max-[860px]:flex-wrap" aria-label="Menu quản trị">
        {menu.map((item) => navItem(item))}
      </nav>
    </aside>

    <div className="flex min-w-0 flex-1 flex-col">
      <header className="admin-topbar sticky top-0 z-10 flex min-h-[82px] items-center justify-between gap-4 border-b border-admin-border bg-white px-8 py-3.5 max-[860px]:min-h-16 max-[860px]:px-4 max-[860px]:py-3">
        <div className="min-w-0"><h1 className="m-0 text-2xl leading-[1.3] font-bold max-[860px]:text-[19px]">{title}</h1><Breadcrumb trail={breadcrumb} onHome={onBreadcrumbHome ?? onHome} /></div>
        <div className="flex items-center gap-4">
          <AdminNotifications />
          <button type="button" className={`flex min-w-0 cursor-pointer items-center gap-[11px] rounded-xl border py-[5px] pr-2.5 pl-[5px] text-left text-inherit transition-colors duration-150 ${accountActive ? 'border-[#dfe6f5] bg-[#f4f7fd]' : 'border-transparent bg-transparent hover:bg-[#f4f6fa]'}`} onClick={onAccount} aria-current={accountActive ? 'page' : undefined} title="Thông tin cá nhân">
            <Avatar user={user} />
            <span className="flex min-w-0 flex-col max-[860px]:hidden"><strong className="max-w-[220px] truncate text-xs leading-normal font-bold">{user.FullName}</strong><span className="text-[10px] text-admin-muted">{role}</span></span>
          </button>
          <button className="ml-1 inline-grid size-[38px] cursor-pointer place-items-center rounded-[10px] border border-[#e2e6ee] bg-white text-[#cf3037] enabled:hover:border-[#f1c4c6] enabled:hover:bg-[#fff5f5] disabled:cursor-progress! disabled:opacity-70!" type="button" onClick={signOut} disabled={auth.loading} aria-label="Đăng xuất" title="Đăng xuất">
            {auth.loading ? <span className="size-[17px] shrink-0 animate-spin rounded-full border-2 border-[#f1c4c6] border-t-[#cf3037]" /> : <Icon name="exit" />}
          </button>
        </div>
      </header>
      <main className="admin-main flex-1 px-8 py-7 max-[860px]:px-4 max-[860px]:py-5">{children}</main>
    </div>
  </div>
}
