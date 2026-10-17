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
import NewsPageRoute from '../pages/NewsPageRoute.jsx'
import NewsWorkspacePageRoute from '../pages/NewsWorkspacePageRoute.jsx'
import BannersPageRoute from '../pages/BannersPageRoute.jsx'
import BannerWorkspacePageRoute from '../pages/BannerWorkspacePageRoute.jsx'
import PaymentMethodsPageRoute from '../pages/PaymentMethodsPageRoute.jsx'
import PaymentMethodWorkspacePageRoute from '../pages/PaymentMethodWorkspacePageRoute.jsx'
import LegacyContentRedirect from '../pages/LegacyContentRedirect.jsx'
import SupportPageRoute from '../pages/SupportPageRoute.jsx'
import ReturnsPageRoute from '../pages/ReturnsPageRoute.jsx'
import ReturnDetailPageRoute from '../pages/ReturnDetailPageRoute.jsx'
import WarrantiesPageRoute from '../pages/WarrantiesPageRoute.jsx'
import WarrantyDetailPageRoute from '../pages/WarrantyDetailPageRoute.jsx'
import ReportsPageRoute from '../pages/ReportsPageRoute.jsx'
import PromotionsPageRoute from '../pages/PromotionsPageRoute.jsx'
import CouponsPageRoute from '../pages/CouponsPageRoute.jsx'
import ShippingMethodsPageRoute from '../pages/ShippingMethodsPageRoute.jsx'
import ShippingMethodWorkspacePageRoute from '../pages/ShippingMethodWorkspacePageRoute.jsx'
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
      { path: 'content', element: <LegacyContentRedirect /> },
      { path: 'payments/new', element: <RequirePermission permission="payment_methods:view"><RequirePermission permission="payment_methods:create"><PaymentMethodWorkspacePageRoute mode="new" /></RequirePermission></RequirePermission> },
      { path: 'payments/:methodId/edit', element: <RequirePermission permission="payment_methods:view"><RequirePermission permission="payment_methods:update"><PaymentMethodWorkspacePageRoute mode="edit" /></RequirePermission></RequirePermission> },
      { path: 'news/new', element: <RequirePermission permission="news:view"><RequirePermission permission="news:create"><NewsWorkspacePageRoute mode="new" /></RequirePermission></RequirePermission> },
      { path: 'news/:articleId', element: <RequirePermission permission="news:view"><NewsWorkspacePageRoute mode="view" /></RequirePermission> },
      { path: 'news/:articleId/edit', element: <RequirePermission permission="news:view"><RequirePermission permission="news:update"><NewsWorkspacePageRoute mode="edit" /></RequirePermission></RequirePermission> },
      { path: 'banners/new', element: <RequirePermission permission="banners:view"><RequirePermission permission="banners:create"><BannerWorkspacePageRoute mode="new" /></RequirePermission></RequirePermission> },
      { path: 'banners/:bannerId', element: <RequirePermission permission="banners:view"><BannerWorkspacePageRoute mode="view" /></RequirePermission> },
      { path: 'banners/:bannerId/edit', element: <RequirePermission permission="banners:view"><RequirePermission permission="banners:update"><BannerWorkspacePageRoute mode="edit" /></RequirePermission></RequirePermission> },
      { path: 'orders/:orderId', element: <RequirePermission permission="orders:view"><OrderDetailPageRoute /></RequirePermission> },
      { path: 'returns/:requestId', element: <RequirePermission permission="returns:view"><ReturnDetailPageRoute /></RequirePermission> },
      { path: 'warranties/:requestId', element: <RequirePermission permission="warranties:view"><WarrantyDetailPageRoute /></RequirePermission> },
      { path: 'purchases/:purchaseId', element: <RequirePermission permission="purchases:view"><PurchaseDetailPageRoute /></RequirePermission> },
      { path: 'purchases/new', element: <RequirePermission permission="purchases:view"><RequirePermission permission="purchases:create"><PurchaseFormPageRoute /></RequirePermission></RequirePermission> },
      { path: 'purchases/:purchaseId/edit', element: <RequirePermission permission="purchases:view"><RequirePermission permission="purchases:update"><PurchaseFormPageRoute /></RequirePermission></RequirePermission> },
      { path: 'reports', element: <RequirePermission permission="revenue_reports:view"><ReportsPageRoute /></RequirePermission> },
      { path: 'promotions', element: <RequirePermission permission="promotions:view"><PromotionsPageRoute /></RequirePermission> },
      { path: 'coupons', element: <RequirePermission permission="promotions:view"><CouponsPageRoute /></RequirePermission> },
      { path: 'shipping-methods', element: <RequirePermission permission="shipping_methods:view"><ShippingMethodsPageRoute /></RequirePermission> },
      { path: 'shipping-methods/new', element: <RequirePermission permission="shipping_methods:view"><RequirePermission permission="shipping_methods:create"><ShippingMethodWorkspacePageRoute mode="new" /></RequirePermission></RequirePermission> },
      { path: 'shipping-methods/:methodId/edit', element: <RequirePermission permission="shipping_methods:view"><RequirePermission permission="shipping_methods:update"><ShippingMethodWorkspacePageRoute mode="edit" /></RequirePermission></RequirePermission> },
      ...ADMIN_SECTIONS.filter((item) => !['overview', 'accounts', 'reports', 'promotions', 'coupons', 'shipping'].includes(item.id)).map((item) => ({
        path: item.path.slice('/admin/'.length),
        element: <RequirePermission permission={item.permission}>{item.id === 'products' ? <ProductsPage /> : item.id === 'categories' ? <CategoriesPage /> : item.id === 'brands' ? <BrandsPageRoute /> : item.id === 'orders' ? <OrdersPageRoute /> : item.id === 'suppliers' ? <SuppliersPageRoute /> : item.id === 'purchases' ? <PurchasesPageRoute /> : item.id === 'reviews' ? <ReviewsPageRoute /> : item.id === 'news' ? <NewsPageRoute /> : item.id === 'banners' ? <BannersPageRoute /> : item.id === 'payments' ? <PaymentMethodsPageRoute /> : item.id === 'support' ? <SupportPageRoute /> : item.id === 'returns' ? <ReturnsPageRoute /> : item.id === 'warranties' ? <WarrantiesPageRoute /> : <AdminResourcePage key={item.id} section={item} />}</RequirePermission>,
      })),
    ],
  },
  { path: '/admin/*', element: <NotFoundPage area="admin" /> },
]
