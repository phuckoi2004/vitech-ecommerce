import RequireCustomer from '../../auth/RequireCustomer.jsx'
import NotFoundPage from '../../components/shared/NotFoundPage.jsx'
import CustomerLayout from '../layouts/CustomerLayout.jsx'
import AccountPage from '../pages/AccountPage.jsx'
import WarrantyCreatePage from '../pages/WarrantyCreatePage.jsx'
import ReturnCreatePage from '../pages/ReturnCreatePage.jsx'
import { RETURN_CREATE_PATH, WARRANTY_CREATE_PATH } from './paths.js'
import ForgotPasswordPage from '../pages/ForgotPasswordPage.jsx'
import HomePage from '../pages/HomePage.jsx'
import LoginPage from '../pages/LoginPage.jsx'
import RegisterPage from '../pages/RegisterPage.jsx'
import CatalogPage from '../pages/CatalogPage.jsx'
import CategoryPage from '../pages/CategoryPage.jsx'
import ProductPage from '../pages/ProductPage.jsx'
import NewsPage from '../pages/NewsPage.jsx'
import ChatPage from '../pages/ChatPage.jsx'
import InfoPage from '../pages/InfoPage.jsx'
import CartPage from '../pages/CartPage.jsx'
import CheckoutPage from '../pages/CheckoutPage.jsx'
import OrderResultPage from '../pages/OrderResultPage.jsx'
import { NotificationsPage, WishlistPage } from '../pages/CustomerLists.jsx'
import { ACCOUNT_PATH, CART_PATH, CHAT_PATH, CHECKOUT_PATH, FORGOT_PASSWORD_PATH, HOME_PATH, INFO_PATHS, LOGIN_PATH, NEWS_PATH, NOTIFICATIONS_PATH, ORDERS_PATH, REGISTER_PATH, SEARCH_PATH, WISHLIST_PATH } from './paths.js'

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
      { path: WARRANTY_CREATE_PATH, element: <RequireCustomer><WarrantyCreatePage /></RequireCustomer> },
      { path: RETURN_CREATE_PATH, element: <RequireCustomer><ReturnCreatePage /></RequireCustomer> },
      { path: SEARCH_PATH, element: <CatalogPage /> },
      { path: '/danh-muc/:slug', element: <CategoryPage /> },
      { path: '/thuong-hieu/:slug', element: <CatalogPage kind="brand" /> },
      { path: '/san-pham/:slug', element: <ProductPage /> },
      { path: NEWS_PATH, element: <NewsPage /> },
      { path: `${NEWS_PATH}/:slug`, element: <NewsPage /> },
      ...Object.entries(INFO_PATHS).map(([page, path]) => ({ path, element: <InfoPage page={page} /> })),
      { path: CART_PATH, element: <RequireCustomer><CartPage /></RequireCustomer> },
      { path: CHECKOUT_PATH, element: <RequireCustomer><CheckoutPage /></RequireCustomer> },
      { path: `${ORDERS_PATH}/:orderId`, element: <RequireCustomer><OrderResultPage /></RequireCustomer> },
      { path: WISHLIST_PATH, element: <RequireCustomer><WishlistPage /></RequireCustomer> },
      { path: NOTIFICATIONS_PATH, element: <RequireCustomer><NotificationsPage /></RequireCustomer> },
      { path: CHAT_PATH, element: <RequireCustomer><ChatPage /></RequireCustomer> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
