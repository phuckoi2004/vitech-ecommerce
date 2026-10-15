import { useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import logoMark from '../../assets/storefront/vietech-mark.png'
import logoName from '../../assets/storefront/vietech-wordmark.png'
import AccountButton from '../components/AccountButton.jsx'
import CartLink from '../components/CartLink.jsx'
import CustomerChat from '../components/CustomerChat.jsx'
import NotificationLink from '../components/NotificationLink.jsx'
import WishlistLink from '../components/WishlistLink.jsx'
import { CHAT_PATH, HOME_PATH, INFO_PATHS, NEWS_PATH, SEARCH_PATH } from '../routes/paths.js'
import './CustomerLayout.css'

// Searches the catalog by product name (GET /products?keyword=…) on the search page.
function SearchForm() {
  const navigate = useNavigate()
  const [keyword, setKeyword] = useState('')

  function submit(event) {
    event.preventDefault()
    const text = keyword.trim()
    if (text) navigate(`${SEARCH_PATH}?q=${encodeURIComponent(text)}`)
  }

  return <form className="shop-search" role="search" onSubmit={submit}>
    <input type="search" name="q" value={keyword} onChange={(event) => setKeyword(event.target.value)}
      placeholder="Tìm kiếm điện thoại, laptop, phụ kiện..." aria-label="Tìm kiếm sản phẩm" maxLength={100} />
    <button type="submit">Tìm kiếm</button>
  </form>
}

const FOOTER_COLUMNS = [
  { title: 'Về VieTech', items: [['Giới thiệu', INFO_PATHS.about], ['Tin tức', NEWS_PATH], ['Liên hệ', INFO_PATHS.contact], ['Hệ thống cửa hàng', INFO_PATHS.stores]] },
  { title: 'Hỗ trợ khách hàng', items: [['Hướng dẫn mua hàng', INFO_PATHS.buyingGuide], ['Thanh toán', INFO_PATHS.payment], ['Vận chuyển', INFO_PATHS.shipping], ['Đổi trả & bảo hành', INFO_PATHS.afterSales]] },
  { title: 'Chính sách', items: [['Bảo mật', INFO_PATHS.privacy], ['Điều khoản sử dụng', INFO_PATHS.terms], ['Đổi trả', INFO_PATHS.returns], ['Bảo hành', INFO_PATHS.warranty]] },
]

// Shared frame of the customer site: header (logo, search, cart, account, notifications, wishlist), page
// content, footer. Used as a layout route (page content in <Outlet />) or around explicit children.
export default function CustomerLayout({ children }) {
  const { pathname } = useLocation()
  return <div className="shop-shell">
    <header className="shop-header">
      <div className="shop-header-inner">
        <Link className="shop-logo" to={HOME_PATH} aria-label="VieTech – Trang chủ">
          <img className="shop-logo-mark" src={logoMark} alt="" width="136" height="83" />
          <img className="shop-logo-wordmark" src={logoName} alt="VieTech" width="189" height="49" />
        </Link>
        <SearchForm />
        <nav className="shop-actions" aria-label="Tài khoản">
          <CartLink />
          <AccountButton />
          <NotificationLink />
          <WishlistLink />
        </nav>
      </div>
    </header>
    <main className="shop-main">{children ?? <Outlet />}</main>
    {pathname.replace(/\/+$/, '') !== CHAT_PATH && <CustomerChat />}
    <footer className="shop-footer" aria-label="Chân trang">
      <div className="shop-footer-inner">
        <div className="shop-footer-brand">
          <p className="shop-footer-name">VieTech</p>
          <p>Nền tảng thương mại điện tử công nghệ, mang sản phẩm chính hãng và dịch vụ tốt đến người Việt.</p>
        </div>
        {FOOTER_COLUMNS.map((column) => <div key={column.title} className="shop-footer-column">
          <h2>{column.title}</h2>
          <ul>
            {column.items.map(([label, to]) => <li key={to}><Link to={to}>{label}</Link></li>)}
          </ul>
        </div>)}
      </div>
    </footer>
  </div>
}
