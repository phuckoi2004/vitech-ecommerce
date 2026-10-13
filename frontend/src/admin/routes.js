export const MENU = [
  { id: 'overview', label: 'Tổng quan' },
  { id: 'accounts', label: 'Tài khoản & phân quyền', permission: 'users:read' },
  { id: 'catalog', label: 'Sản phẩm', children: [
    { id: 'products', label: 'Danh sách sản phẩm', permission: 'products:view' },
    { id: 'categories', label: 'Danh mục', permission: 'categories:view' },
    { id: 'brands', label: 'Thương hiệu', permission: 'brands:view' },
    { id: 'promotions', label: 'Khuyến mãi', permission: 'promotions:view' },
  ] },
  { id: 'orders', label: 'Đơn hàng', permission: 'orders:view' },
  { id: 'purchases', label: 'Nhập hàng', permission: 'purchases:view' },
  { id: 'inventory', label: 'Kho hàng', permission: 'inventory:view' },
  { id: 'returns', label: 'Đổi / Trả', permission: 'returns:view' },
  { id: 'warranties', label: 'Bảo hành', permission: 'warranties:view' },
  { id: 'reviews', label: 'Đánh giá', permission: 'reviews:view' },
  { id: 'content', label: 'Tin tức & Banner', permission: 'news:view' },
  { id: 'reports', label: 'Báo cáo thống kê', permission: 'revenue_reports:view' },
  { id: 'support', label: 'Hỗ trợ khách hàng', permission: 'chat:view' },
  { id: 'payments', label: 'Thanh toán', permission: 'payment_methods:view' },
]

export const PROFILE = { id: 'profile', label: 'Thông tin cá nhân' }

export function allowedMenu(permissions) {
  return MENU.filter((item) => !item.permission || permissions.includes(item.permission))
    .map((item) => item.children ? { ...item, children: item.children.filter((child) => permissions.includes(child.permission)) } : item)
    .filter((item) => !item.children || item.children.length)
}

export function sectionFromPath(pathname) {
  return pathname.replace(/\/+$/, '').split('/')[2] || 'overview'
}

export function sectionPath(id) {
  return id === 'overview' ? '/admin' : `/admin/${id}`
}
