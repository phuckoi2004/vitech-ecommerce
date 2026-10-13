import Icon from '../components/Icon.jsx'
import './AdminLayout.css'

const ROLES = { Staff: 'Nhân viên', Admin: 'Quản trị viên' }

function initials(name = '') {
  const words = name.trim().split(/\s+/).filter(Boolean)
  return (words.length > 1 ? words[0][0] + words.at(-1)[0] : words[0]?.[0] ?? '?').toUpperCase()
}

export function Avatar({ user, className = '' }) {
  return user.AvatarUrl
    ? <img className={`admin-avatar ${className}`} src={user.AvatarUrl} alt="" />
    : <span className={`admin-avatar ${className}`} aria-hidden="true">{initials(user.FullName)}</span>
}

// "Trang chủ / A / B": the first segment links back to the home section.
function Breadcrumb({ trail, onHome }) {
  const [home, ...rest] = trail.split(' / ')
  return <p className="admin-breadcrumb">
    <button type="button" className="admin-breadcrumb-home" onClick={onHome}>{home}</button>
    {rest.map((part) => <span key={part}> / {part}</span>)}
  </p>
}

export default function AdminLayout({ auth, title, breadcrumb, menu = [], active, onSelect, onHome, onAccount, accountActive = false, children }) {
  const { user } = auth
  const role = ROLES[user.Role] ?? user.Role

  async function signOut() {
    try { await auth.signOut() } catch { /* The hook displays a connection error on the login screen. */ }
  }

  return <div className="admin-shell">
    <aside className="admin-sidebar" aria-label="Thanh điều hướng quản trị">
      <button type="button" className="admin-brand" onClick={onHome} title="Về trang chủ"><strong>VIETECH</strong></button>
      <nav className="admin-nav" aria-label="Menu quản trị">
        {menu.map((item) => <button key={item.id} type="button" className={`admin-nav-item ${item.id === active ? 'is-active' : ''}`} aria-current={item.id === active ? 'page' : undefined} onClick={() => onSelect(item.id)}>{item.label}</button>)}
      </nav>
    </aside>

    <div className="admin-main">
      <header className="admin-topbar">
        <div className="admin-title"><h1>{title}</h1><Breadcrumb trail={breadcrumb} onHome={onHome} /></div>
        <div className="admin-account">
          <button type="button" className={`admin-account-button ${accountActive ? 'is-active' : ''}`} onClick={onAccount} aria-current={accountActive ? 'page' : undefined} title="Thông tin cá nhân">
            <Avatar user={user} />
            <span className="admin-account-text"><strong>{user.FullName}</strong><span>{role}</span></span>
          </button>
          <button className="admin-signout" type="button" onClick={signOut} disabled={auth.loading} aria-label="Đăng xuất" title="Đăng xuất">
            {auth.loading ? <span className="spinner" /> : <Icon name="exit" />}
          </button>
        </div>
      </header>
      <main className="admin-content">{children}</main>
    </div>
  </div>
}
