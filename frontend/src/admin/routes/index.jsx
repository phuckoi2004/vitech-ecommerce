import RequireInternal from '../../auth/RequireInternal.jsx'
import RequirePermission from '../../auth/RequirePermission.jsx'
import NotFoundPage from '../../components/shared/NotFoundPage.jsx'
import AdminAuthPage from '../pages/AdminAuthPage.jsx'
import AdminHomePage from '../pages/AdminHomePage.jsx'
import { AdminProfileSection, AdminUsersSection } from '../pages/AdminSections.jsx'
import DashboardPage from '../pages/DashboardPage.jsx'
import AdminResourcePage from '../pages/AdminResourcePage.jsx'
import ProductsPage from '../pages/ProductsPage.jsx'
import CategoriesPage from '../pages/CategoriesPage.jsx'
import BrandsPageRoute from '../pages/BrandsPageRoute.jsx'
import OrdersPageRoute from '../pages/OrdersPageRoute.jsx'
import OrderDetailPageRoute from '../pages/OrderDetailPageRoute.jsx'
import SuppliersPageRoute from '../pages/SuppliersPageRoute.jsx'
import PurchasesPageRoute from '../pages/PurchasesPageRoute.jsx'
import PurchaseDetailPageRoute from '../pages/PurchaseDetailPageRoute.jsx'
import PurchaseFormPageRoute from '../pages/PurchaseFormPageRoute.jsx'
import ReviewsPageRoute from '../pages/ReviewsPageRoute.jsx'
import { ADMIN_SECTIONS } from './menu.js'
import { ADMIN_FORGOT_PASSWORD_PATH, ADMIN_HOME_PATH, ADMIN_LOGIN_PATH } from './paths.js'

// Internal area for Staff/Admin (English URLs). Unknown /admin/* URLs show the 404 page, signed in or not.
export const adminRoutes = [
  { path: ADMIN_LOGIN_PATH, element: <AdminAuthPage page="login" /> },
  { path: ADMIN_FORGOT_PASSWORD_PATH, element: <AdminAuthPage page="reset" /> },
  {
    path: ADMIN_HOME_PATH,
    element: <RequireInternal><AdminHomePage /></RequireInternal>,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'users', element: <AdminUsersSection /> },
      { path: 'profile', element: <AdminProfileSection /> },
      { path: 'orders/:orderId', element: <RequirePermission permission="orders:view"><OrderDetailPageRoute /></RequirePermission> },
      { path: 'purchases/:purchaseId', element: <RequirePermission permission="purchases:view"><PurchaseDetailPageRoute /></RequirePermission> },
      { path: 'purchases/new', element: <RequirePermission permission="purchases:view"><RequirePermission permission="purchases:create"><PurchaseFormPageRoute /></RequirePermission></RequirePermission> },
      { path: 'purchases/:purchaseId/edit', element: <RequirePermission permission="purchases:view"><RequirePermission permission="purchases:update"><PurchaseFormPageRoute /></RequirePermission></RequirePermission> },
      ...ADMIN_SECTIONS.filter((item) => !['overview', 'accounts'].includes(item.id)).map((item) => ({
        path: item.path.slice('/admin/'.length),
        element: <RequirePermission permission={item.permission}>{item.id === 'products' ? <ProductsPage /> : item.id === 'categories' ? <CategoriesPage /> : item.id === 'brands' ? <BrandsPageRoute /> : item.id === 'orders' ? <OrdersPageRoute /> : item.id === 'suppliers' ? <SuppliersPageRoute /> : item.id === 'purchases' ? <PurchasesPageRoute /> : item.id === 'reviews' ? <ReviewsPageRoute /> : <AdminResourcePage key={item.id} section={item} />}</RequirePermission>,
      })),
    ],
  },
  { path: '/admin/*', element: <NotFoundPage area="admin" /> },
]
