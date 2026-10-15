import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import AdminLayout from '../layouts/AdminLayout.jsx'
import { ADMIN_MENU, ADMIN_PROFILE_ITEM, ADMIN_SECTIONS, visibleMenu } from '../routes/menu.js'
import orderLogo from '../assets/order-logo.png'
import { NEWS_PAGE_TITLES } from '../lib/news.js'
import { BANNER_PAGE_TITLES } from '../lib/banners.js'
import { PAYMENT_PAGE_TITLES } from '../lib/payment-methods.js'
import { SHIPPING_PAGE_TITLES } from '../lib/shipping-methods.js'

const CATALOG_HEADERS = {
  categories: { title: 'Quản lý danh mục', breadcrumb: 'Sản phẩm / Quản lý danh mục' },
  brands: { title: 'Quản lý Thương hiệu', breadcrumb: 'Sản phẩm / Thương hiệu' },
  payments: { title: 'Quản lý thanh toán', breadcrumb: 'Trang chủ / Thanh toán' },
  returns: { title: 'Quản lý đổi trả', breadcrumb: 'Trang chủ / Đổi trả' },
  warranties: { title: 'Quản lý bảo hành', breadcrumb: 'Trang chủ / Bảo hành' },
  shipping: { title: 'Quản lý phương thức vận chuyển', breadcrumb: 'Trang chủ / Vận chuyển / Phương thức vận chuyển' },
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
  const warrantyDetail = /^\/admin\/warranties\/[^/]+$/.test(path)
  const returnDetail = /^\/admin\/returns\/[^/]+$/.test(path)
  const purchaseNew = path === '/admin/purchases/new'
  const purchaseEdit = /^\/admin\/purchases\/[^/]+\/edit$/.test(path)
  const purchaseDetail = !purchaseNew && /^\/admin\/purchases\/[^/]+$/.test(path)
  const purchaseTitle = purchaseNew ? 'Tạo phiếu nhập' : purchaseEdit ? 'Sửa phiếu nhập' : purchaseDetail ? 'Chi tiết phiếu nhập' : ''
  const newsPage = path.startsWith('/admin/news/')
  const newsTitle = newsPage ? NEWS_PAGE_TITLES[path === '/admin/news/new' ? 'new' : path.endsWith('/edit') ? 'edit' : 'view'] : ''
  const bannerPage = path.startsWith('/admin/banners/')
  const bannerTitle = bannerPage ? BANNER_PAGE_TITLES[path === '/admin/banners/new' ? 'new' : path.endsWith('/edit') ? 'edit' : 'view'] : ''
  const paymentPage = path === '/admin/payments/new' || /^\/admin\/payments\/[^/]+\/edit$/.test(path)
  const paymentTitle = paymentPage ? PAYMENT_PAGE_TITLES[path === '/admin/payments/new' ? 'new' : 'edit'] : ''
  const shippingPage = path === '/admin/shipping-methods/new' || /^\/admin\/shipping-methods\/[^/]+\/edit$/.test(path)
  const shippingTitle = shippingPage ? SHIPPING_PAGE_TITLES[path === '/admin/shipping-methods/new' ? 'new' : 'edit'] : ''
  const menu = visibleMenu(auth.permissions)
  const current = path === ADMIN_PROFILE_ITEM.path ? ADMIN_PROFILE_ITEM : ADMIN_SECTIONS.find((item) => item.path === path || (orderDetail && item.id === 'orders') || (returnDetail && item.id === 'returns') || (warrantyDetail && item.id === 'warranties') || (purchaseTitle && item.id === 'purchases') || (newsPage && item.id === 'news') || (bannerPage && item.id === 'banners') || (paymentPage && item.id === 'payments') || (shippingPage && item.id === 'shipping')) ?? ADMIN_MENU[0]
  const catalogHeader = warrantyDetail ? { title: 'Chi tiết bảo hành', breadcrumb: 'Bảo hành / Chi tiết yêu cầu' } : returnDetail ? { title: 'Chi tiết đổi trả', breadcrumb: 'Đổi trả / Chi tiết yêu cầu' } : paymentTitle ? { title: paymentTitle, breadcrumb: 'Trang chủ / Thanh toán / ' + paymentTitle } : productTitle ? { title: productTitle, breadcrumb: 'Sản phẩm / Danh sách sản phẩm / ' + productTitle } : CATALOG_HEADERS[current.id]
  const contentSection = ['news', 'banners'].includes(current.id)
  const contentTitle = newsTitle || bannerTitle
  const contentHeader = contentSection ? { title: contentTitle || (current.id === 'news' ? 'Quản lý tin tức' : 'Quản lý banner quảng cáo'), breadcrumb: 'Trang chủ / Tin tức & Banner / ' + (current.id === 'banners' ? 'Banner quảng cáo' : current.label) + (contentTitle ? ' / ' + contentTitle : '') } : null
  // A page inside a section (e.g. "Thêm tài khoản") extends the breadcrumb; it belongs to the URL it was set on.
  const [subPage, setSubPage] = useState(null)
  // Choosing a menu entry again starts that section fresh (e.g. back to the list).
  const [visit, setVisit] = useState(0)
  const subPageLabel = subPage?.path === path ? subPage.label : null
  const onSubPage = useCallback((label) => setSubPage(label ? { path, label } : null), [path])

  useEffect(() => {
    document.title = `${shippingTitle || (warrantyDetail ? 'Chi tiết bảo hành' : returnDetail ? 'Chi tiết đổi trả' : '') || paymentTitle || contentTitle || productTitle || purchaseTitle || subPageLabel || current.label} | VieTech`
  }, [current, subPageLabel, purchaseTitle, productTitle, contentTitle, paymentTitle, returnDetail, warrantyDetail, shippingTitle])

  function open(item) {
    if (!item) return
    setSubPage(null)
    setVisit((value) => value + 1)
    navigate(item.path)
  }

  return <AdminLayout auth={auth} sidebarLogo={orderDetail ? orderLogo : undefined} title={orderDetail ? 'Chi tiết đơn hàng' : contentHeader?.title || purchaseTitle || (current.id === 'overview' ? 'Dashboard' : current.id === 'orders' ? 'Quản lý đơn hàng' : current.id === 'suppliers' ? 'Quản lý nhà cung cấp' : current.id === 'purchases' ? 'Quản lý nhập hàng' : current.id === 'reviews' ? 'Quản lý đánh giá' : catalogHeader?.title ?? current.label)} breadcrumb={contentHeader?.breadcrumb || (current.id === 'purchases' ? 'Nhập hàng / ' + (purchaseTitle || 'Danh sách phiếu nhập') : catalogHeader?.breadcrumb ?? `Trang chủ / ${current.label}${subPageLabel ? ` / ${subPageLabel}` : ''}`)}
    onBreadcrumbHome={returnDetail || warrantyDetail || shippingPage ? () => open(current) : current.id === 'purchases' ? () => open(current) : catalogHeader && !['payments', 'returns', 'warranties', 'shipping'].includes(current.id) ? () => open(ADMIN_SECTIONS.find((item) => item.id === 'products')) : undefined}
    menu={menu} active={current.id} onSelect={(id) => open(menu.flatMap((item) => item.children ?? item).find((item) => item.id === id))} onHome={() => open(ADMIN_MENU[0])}
    onAccount={() => open(ADMIN_PROFILE_ITEM)} accountActive={current.id === ADMIN_PROFILE_ITEM.id}>
    <Outlet context={{ onSubPage, visit }} />
  </AdminLayout>
}
