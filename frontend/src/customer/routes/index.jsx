import RequireCustomer from '../../auth/RequireCustomer.jsx'
import NotFoundPage from '../../components/shared/NotFoundPage.jsx'
import CustomerLayout from '../layouts/CustomerLayout.jsx'
import AccountPage from '../pages/AccountPage.jsx'
import ForgotPasswordPage from '../pages/ForgotPasswordPage.jsx'
import HomePage from '../pages/HomePage.jsx'
import LoginPage from '../pages/LoginPage.jsx'
import RegisterPage from '../pages/RegisterPage.jsx'
import { ACCOUNT_PATH, FORGOT_PASSWORD_PATH, HOME_PATH, LOGIN_PATH, REGISTER_PATH } from './paths.js'

// Customer site (Vietnamese URLs). Auth pages use their own two-column frame; other pages share CustomerLayout.
// Unknown URLs outside /admin show the 404 page inside the customer layout.
export const customerRoutes = [
  { path: LOGIN_PATH, element: <LoginPage /> },
  { path: REGISTER_PATH, element: <RegisterPage /> },
  { path: FORGOT_PASSWORD_PATH, element: <ForgotPasswordPage /> },
  {
    element: <CustomerLayout />,
    children: [
      { path: HOME_PATH, element: <HomePage /> },
      { path: ACCOUNT_PATH, element: <RequireCustomer><AccountPage /></RequireCustomer> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
