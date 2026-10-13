import { Link, Outlet } from 'react-router-dom'
import logo from '../../assets/auth/vietech-logo.png'
import AccountButton from '../components/AccountButton.jsx'
import { HOME_PATH } from '../routes/paths.js'
import './CustomerLayout.css'

// Shared frame of the customer site: header with the logo, page content, footer.
// Used as a layout route (page content in <Outlet />) or around explicit children.
// Search, cart and footer links are added once their pages exist.
export default function CustomerLayout({ children }) {
  return <div className="shop-shell">
    <header className="shop-header">
      <div className="shop-container shop-header-inner">
        <Link className="shop-logo" to={HOME_PATH} aria-label="VieTech – Trang chủ">
          <img src={logo} alt="VieTech" width="2172" height="724" />
        </Link>
        {/* Right-hand actions; the cart and other links join this group later. */}
        <nav className="shop-actions" aria-label="Tài khoản">
          <AccountButton />
        </nav>
      </div>
    </header>
    <main className="shop-main">{children ?? <Outlet />}</main>
    <footer className="shop-footer" aria-label="Chân trang">
      <div className="shop-container" />
    </footer>
  </div>
}
