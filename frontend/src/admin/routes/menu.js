import { ADMIN_HOME_PATH, ADMIN_PROFILE_PATH, ADMIN_USERS_PATH } from './paths.js'

// Sidebar entries. `permission` is a code from the session's permission list (backend app/core/rbac.py, returned by
// /auth/login, /auth/refresh and /auth/me); it only hides the entry, the backend still enforces every request.
export const ADMIN_MENU = [
  { id: 'overview', label: 'Tổng quan', path: ADMIN_HOME_PATH },
  { id: 'accounts', label: 'Tài khoản', path: ADMIN_USERS_PATH, permission: 'users:read' },
  { id: 'catalog', label: 'Sản phẩm', children: [
    { id: 'products', label: 'Danh sách sản phẩm', path: '/admin/products', permission: 'products:view' },
    { id: 'categories', label: 'Danh mục', path: '/admin/categories', permission: 'categories:view' },
    { id: 'brands', label: 'Thương hiệu', path: '/admin/brands', permission: 'brands:view' },
  ] },
  { id: 'discounts', label: 'Khuyến mãi', children: [
    { id: 'promotions', label: 'Chương trình khuyến mãi', path: '/admin/promotions', permission: 'promotions:view' },
    { id: 'coupons', label: 'Mã giảm giá', path: '/admin/coupons', permission: 'promotions:view' },
  ] },
  { id: 'orders', label: 'Đơn hàng', path: '/admin/orders', permission: 'orders:view' },
  { id: 'purchases', label: 'Nhập hàng', path: '/admin/purchases', permission: 'purchases:view' },
  { id: 'suppliers', label: 'Nhà cung cấp', path: '/admin/suppliers', permission: 'suppliers:view' },
  { id: 'returns', label: 'Đổi trả', path: '/admin/returns', permission: 'returns:view' },
  { id: 'warranties', label: 'Bảo hành', path: '/admin/warranties', permission: 'warranties:view' },
  { id: 'reviews', label: 'Đánh giá', path: '/admin/reviews', permission: 'reviews:view' },
  { id: 'content', label: 'Tin tức & Banner', children: [
    { id: 'news', label: 'Tin tức', path: '/admin/news', permission: 'news:view' },
    { id: 'banners', label: 'Banner', path: '/admin/banners', permission: 'banners:view' },
  ] },
  { id: 'reports', label: 'Báo cáo thống kê', path: '/admin/reports', permission: 'revenue_reports:view' },
  { id: 'support', label: 'Hỗ trợ khách hàng', path: '/admin/support', permission: 'chat:view' },
  { id: 'payments', label: 'Thanh toán', path: '/admin/payments', permission: 'payment_methods:view' },
  { id: 'shipping', label: 'Vận chuyển', path: '/admin/shipping-methods', permission: 'shipping_methods:view' },
]

// Opened from the account button in the top bar, not from the menu.
export const ADMIN_PROFILE_ITEM = { id: 'profile', label: 'Thông tin cá nhân', path: ADMIN_PROFILE_PATH }

export function visibleMenu(permissions) {
  return ADMIN_MENU.filter((item) => !item.permission || permissions.includes(item.permission))
    .map((item) => item.children ? { ...item, children: item.children.filter((child) => permissions.includes(child.permission)) } : item)
    .filter((item) => !item.children || item.children.length)
}

// Keep inventory deep links (e.g. dashboard low-stock alerts) available after replacing its sidebar entry.
export const ADMIN_INVENTORY_ITEM = { id: 'inventory', label: 'Kho hàng', path: '/admin/inventory', permission: 'inventory:view' }
export const ADMIN_SECTIONS = [...ADMIN_MENU.flatMap((item) => item.children ?? item), ADMIN_INVENTORY_ITEM]
