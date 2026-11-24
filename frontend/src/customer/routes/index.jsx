import RequireCustomer from '../../auth/RequireCustomer.jsx'
import NotFoundPage from '../../components/shared/NotFoundPage.jsx'
import CustomerLayout from '../layouts/CustomerLayout.jsx'
import { lazyPage } from '../../components/shared/LazyPage.jsx'
import { RETURN_CREATE_PATH, WARRANTY_CREATE_PATH } from './paths.js'
import HomePage from '../pages/HomePage.jsx'
import { ACCOUNT_PATH, CART_PATH, CHAT_PATH, CHECKOUT_PATH, FORGOT_PASSWORD_PATH, HOME_PATH, INFO_PATHS, LOGIN_PATH, NEWS_PATH, NOTIFICATIONS_PATH, ORDERS_PATH, REGISTER_PATH, SEARCH_PATH, WISHLIST_PATH } from './paths.js'

const AccountPage = lazyPage(() => import('../pages/AccountPage.jsx'))
const WarrantyCreatePage = lazyPage(() => import('../pages/WarrantyCreatePage.jsx'))
const ReturnCreatePage = lazyPage(() => import('../pages/ReturnCreatePage.jsx'))
const ForgotPasswordPage = lazyPage(() => import('../pages/ForgotPasswordPage.jsx'))
const LoginPage = lazyPage(() => import('../pages/LoginPage.jsx'))
const RegisterPage = lazyPage(() => import('../pages/RegisterPage.jsx'))
const CatalogPage = lazyPage(() => import('../pages/CatalogPage.jsx'))
const CategoryPage = lazyPage(() => import('../pages/CategoryPage.jsx'))
const ProductPage = lazyPage(() => import('../pages/ProductPage.jsx'))
const NewsPage = lazyPage(() => import('../pages/NewsPage.jsx'))
const ChatPage = lazyPage(() => import('../pages/ChatPage.jsx'))
const InfoPage = lazyPage(() => import('../pages/InfoPage.jsx'))
const CartPage = lazyPage(() => import('../pages/CartPage.jsx'))
const CheckoutPage = lazyPage(() => import('../pages/CheckoutPage.jsx'))
const OrderResultPage = lazyPage(() => import('../pages/OrderResultPage.jsx'))
const NotificationsPage = lazyPage(() => import('../pages/CustomerLists.jsx'), 'NotificationsPage')
const WishlistPage = lazyPage(() => import('../pages/CustomerLists.jsx'), 'WishlistPage')

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
