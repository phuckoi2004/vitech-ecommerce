import AdminAuthPage from './admin/pages/AdminAuthPage.jsx'
import AccountPage from './customer/pages/AccountPage.jsx'
import ForgotPasswordPage from './customer/pages/ForgotPasswordPage.jsx'
import HomePage from './customer/pages/HomePage.jsx'
import LoginPage from './customer/pages/LoginPage.jsx'
import RegisterPage from './customer/pages/RegisterPage.jsx'
import { ACCOUNT_PATH, FORGOT_PASSWORD_PATH, LOGIN_PATH, REGISTER_PATH } from './customer/routes/paths.js'
import './App.css'

// /admin/* is the internal area for staff and admins; everything else is the customer site.
function isAdminPath(pathname) {
  return pathname === '/admin' || pathname.startsWith('/admin/')
}

// Customer pages by path; unknown paths show the home page.
const CUSTOMER_PAGES = { [LOGIN_PATH]: LoginPage, [REGISTER_PATH]: RegisterPage, [FORGOT_PASSWORD_PATH]: ForgotPasswordPage, [ACCOUNT_PATH]: AccountPage }

export default function App() {
  const pathname = window.location.pathname.replace(/\/+$/, '') || '/'
  if (isAdminPath(pathname)) return <AdminAuthPage />
  const Page = CUSTOMER_PAGES[pathname] ?? HomePage
  return <Page />
}
