import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import AdminLayout from '../layouts/AdminLayout.jsx'
import { ADMIN_MENU, ADMIN_PROFILE_ITEM, ADMIN_SECTIONS, visibleMenu } from '../routes/menu.js'
import orderLogo from '../assets/order-logo.png'

const CATALOG_HEADERS = {
  categories: { title: 'Quản lý danh mục', breadcrumb: 'Sản phẩm / Quản lý danh mục' },
  brands: { title: 'Quản lý Thương hiệu', breadcrumb: 'Sản phẩm / Thương hiệu' },
}

// Internal layout: the route table owns every section, including the dashboard index.
export default function AdminHomePage() {
  const auth = useInternalAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const path = pathname.replace(/\/+$/, '') || '/'
  const [params] = useSearchParams()
  const productMode = path === '/admin/products' ? params.get('dialog') : null
  const productTitle = ({ view: 'Chi tiết sản phẩm', new: 'Thêm sản phẩm', edit: 'Cập nhật sản phẩm' })[productMode] || ''
  const orderDetail = /^\/admin\/orders\/[^/]+$/.test(path)
  const purchaseNew = path === '/admin/purchases/new'
  const purchaseEdit = /^\/admin\/purchases\/[^/]+\/edit$/.test(path)
  const purchaseDetail = !purchaseNew && /^\/admin\/purchases\/[^/]+$/.test(path)
  const purchaseTitle = purchaseNew ? 'Tạo phiếu nhập' : purchaseEdit ? 'Sửa phiếu nhập' : purchaseDetail ? 'Chi tiết phiếu nhập' : ''
  const menu = visibleMenu(auth.permissions)
  const current = path === ADMIN_PROFILE_ITEM.path ? ADMIN_PROFILE_ITEM : ADMIN_SECTIONS.find((item) => item.path === path || (orderDetail && item.id === 'orders') || (purchaseTitle && item.id === 'purchases')) ?? ADMIN_MENU[0]
  const catalogHeader = productTitle ? { title: productTitle, breadcrumb: 'Sản phẩm / Danh sách sản phẩm / ' + productTitle } : CATALOG_HEADERS[current.id]
  // A page inside a section (e.g. "Thêm tài khoản") extends the breadcrumb; it belongs to the URL it was set on.
  const [subPage, setSubPage] = useState(null)
  // Choosing a menu entry again starts that section fresh (e.g. back to the list).
  const [visit, setVisit] = useState(0)
  const subPageLabel = subPage?.path === path ? subPage.label : null
  const onSubPage = useCallback((label) => setSubPage(label ? { path, label } : null), [path])

  useEffect(() => {
    document.title = `${productTitle || purchaseTitle || subPageLabel || current.label} | VieTech`
  }, [current, subPageLabel, purchaseTitle, productTitle])

  function open(item) {
    if (!item) return
    setSubPage(null)
    setVisit((value) => value + 1)
    navigate(item.path)
  }

  return <AdminLayout auth={auth} sidebarLogo={orderDetail ? orderLogo : undefined} title={orderDetail ? 'Chi tiết đơn hàng' : purchaseTitle || (current.id === 'overview' ? 'Dashboard' : current.id === 'orders' ? 'Quản lý đơn hàng' : current.id === 'suppliers' ? 'Quản lý nhà cung cấp' : current.id === 'purchases' ? 'Quản lý nhập hàng' : current.id === 'reviews' ? 'Quản lý đánh giá' : catalogHeader?.title ?? current.label)} breadcrumb={current.id === 'purchases' ? 'Nhập hàng / ' + (purchaseTitle || 'Danh sách phiếu nhập') : catalogHeader?.breadcrumb ?? `Trang chủ / ${current.label}${subPageLabel ? ` / ${subPageLabel}` : ''}`}
    onBreadcrumbHome={current.id === 'purchases' ? () => open(current) : catalogHeader ? () => open(ADMIN_SECTIONS.find((item) => item.id === 'products')) : undefined}
    menu={menu} active={current.id} onSelect={(id) => open(menu.flatMap((item) => item.children ?? item).find((item) => item.id === id))} onHome={() => open(ADMIN_MENU[0])}
    onAccount={() => open(ADMIN_PROFILE_ITEM)} accountActive={current.id === ADMIN_PROFILE_ITEM.id}>
    <Outlet context={{ onSubPage, visit }} />
  </AdminLayout>
}
