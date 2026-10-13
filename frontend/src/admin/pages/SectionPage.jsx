import { useState } from 'react'
import { currentMonth, monthPeriod } from '../../lib/admin-dashboard-api.js'
import useAdminData from '../hooks/useAdminData.js'
import DataTable, { DataError, formatDate, formatMoney, ORDER_COLUMNS } from '../components/DataTable.jsx'

const column = (key, label, render) => ({ key, label, render })
const activeLabel = (value) => value ? 'Hoạt động' : 'Ngừng hoạt động'
const STATUS_LABELS = {
  Pending: 'Chờ xử lý', Approved: 'Đã duyệt', Rejected: 'Từ chối', Receiving: 'Đang nhận hàng', Processing: 'Đang xử lý',
  Completed: 'Hoàn thành', Cancelled: 'Đã hủy', Closed: 'Đã đóng', Open: 'Đang mở', New: 'Mới', HandedOver: 'Đã bàn giao',
  Draft: 'Bản nháp', Active: 'Hoạt động', Inactive: 'Tạm ẩn', Discontinued: 'Ngừng kinh doanh', Scheduled: 'Đã lên lịch',
  Expired: 'Hết hạn', Published: 'Đã xuất bản', Hidden: 'Đã ẩn', Paid: 'Đã thanh toán', Success: 'Thành công', Failed: 'Thất bại', Refunded: 'Đã hoàn tiền',
}
const statusLabel = (value) => STATUS_LABELS[value] ?? value

// Read-only section tables use existing APIs; workflow forms can be added independently.
const SECTIONS = {
  products: [{ label: 'Sản phẩm', path: '/admin/products', rowKey: 'ProductId', columns: [column('Name', 'Tên sản phẩm'), column('Status', 'Trạng thái', statusLabel), column('SoldQuantity', 'Đã bán'), column('CreatedAt', 'Ngày tạo', formatDate)] }],
  categories: [{ label: 'Danh mục', path: '/categories', params: { active_only: false }, rowKey: 'CategoryId', columns: [column('Name', 'Tên danh mục'), column('Slug', 'Đường dẫn'), column('DisplayOrder', 'Thứ tự'), column('IsActive', 'Trạng thái', activeLabel)] }],
  brands: [{ label: 'Thương hiệu', path: '/brands', params: { active_only: false }, rowKey: 'BrandId', columns: [column('Name', 'Thương hiệu'), column('Slug', 'Đường dẫn'), column('IsActive', 'Trạng thái', activeLabel)] }],
  promotions: [{ label: 'Khuyến mãi', path: '/admin/promotions', rowKey: 'PromotionId', columns: [column('Name', 'Chương trình'), column('Status', 'Trạng thái', statusLabel), column('StartDate', 'Bắt đầu', formatDate), column('EndDate', 'Kết thúc', formatDate)] }],
  orders: [{ label: 'Đơn hàng', path: '/admin/orders', rowKey: 'OrderId', columns: ORDER_COLUMNS }],
  purchases: [
    { label: 'Phiếu nhập hàng', path: '/admin/purchase-orders', rowKey: 'PurchaseOrderId', columns: [column('PurchaseOrderCode', 'Mã phiếu'), column('TotalAmount', 'Giá trị', formatMoney), column('Status', 'Trạng thái', statusLabel), column('CreatedAt', 'Ngày tạo', formatDate)] },
    { label: 'Nhà cung cấp', permission: 'suppliers:view', path: '/admin/suppliers', rowKey: 'SupplierId', columns: [column('SupplierCode', 'Mã nhà cung cấp'), column('Name', 'Tên nhà cung cấp'), column('PhoneNumber', 'Số điện thoại'), column('IsActive', 'Trạng thái', activeLabel)] },
  ],
  inventory: [
    { label: 'Tồn kho', path: '/admin/statistics/inventory', rowKey: 'ProductVariantId', columns: [column('ProductName', 'Sản phẩm'), column('VariantName', 'Biến thể'), column('Sku', 'SKU'), column('StockQuantity', 'Tồn kho'), column('MinStockLevel', 'Ngưỡng cảnh báo')] },
    { label: 'Sắp hết hàng', path: '/admin/inventory/low-stock', rowKey: 'ProductVariantId', columns: [column('Sku', 'SKU'), column('VariantName', 'Biến thể'), column('StockQuantity', 'Tồn kho'), column('MinStockLevel', 'Ngưỡng cảnh báo')] },
  ],
  returns: [{ label: 'Đổi / Trả', path: '/admin/return-requests', rowKey: 'ReturnRequestId', columns: [column('RequestCode', 'Mã yêu cầu'), column('RequestType', 'Loại yêu cầu', (value) => value === 'Exchange' ? 'Đổi hàng' : 'Trả hàng'), column('Quantity', 'Số lượng'), column('Status', 'Trạng thái', statusLabel), column('RequestedAt', 'Ngày yêu cầu', formatDate)] }],
  warranties: [{ label: 'Bảo hành', path: '/admin/warranty-requests', rowKey: 'WarrantyRequestId', columns: [column('RequestCode', 'Mã yêu cầu'), column('IssueDescription', 'Mô tả lỗi'), column('Status', 'Trạng thái', statusLabel), column('RequestedAt', 'Ngày yêu cầu', formatDate)] }],
  content: [
    { label: 'Tin tức', path: '/admin/news', rowKey: 'NewsArticleId', columns: [column('Title', 'Tiêu đề'), column('Status', 'Trạng thái', statusLabel), column('CreatedAt', 'Ngày tạo', formatDate)] },
    { label: 'Banner', permission: 'banners:view', path: '/admin/banners', rowKey: 'BannerId', columns: [column('Title', 'Tiêu đề'), column('DisplayOrder', 'Thứ tự'), column('IsActive', 'Trạng thái', activeLabel), column('StartDate', 'Bắt đầu', formatDate), column('EndDate', 'Kết thúc', formatDate)] },
  ],
  payments: [
    { label: 'Phương thức thanh toán', path: '/payment-methods', params: { active_only: false }, rowKey: 'PaymentMethodId', columns: [column('Code', 'Mã'), column('Name', 'Phương thức'), column('IsActive', 'Trạng thái', activeLabel)] },
    { label: 'Giao dịch', path: '/admin/payment-transactions', rowKey: 'PaymentTransactionId', columns: [column('GatewayTransactionCode', 'Mã giao dịch'), column('TransactionType', 'Loại', (value) => value === 'Refund' ? 'Hoàn tiền' : 'Thanh toán'), column('Amount', 'Số tiền', formatMoney), column('Status', 'Trạng thái', statusLabel), column('CreatedAt', 'Ngày tạo', formatDate)] },
  ],
}

function Pagination({ page, total, pageSize = 20, loading, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return <div className="mt-[18px] flex flex-wrap items-center justify-end gap-3 text-xs text-admin-muted"><span>{total} bản ghi · Trang {page} / {pages}</span>
    <button type="button" className="cursor-pointer rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text" disabled={loading || page <= 1} onClick={() => onPage(page - 1)}>Trước</button>
    <button type="button" className="cursor-pointer rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text" disabled={loading || page >= pages} onClick={() => onPage(page + 1)}>Sau</button>
  </div>
}

function ListView({ auth, config, params = {} }) {
  const [page, setPage] = useState(1)
  const [version, setVersion] = useState(0)
  const state = useAdminData(auth.withAccessToken, config.path, { page, page_size: 20, ...config.params, ...params }, version)
  const isArray = Array.isArray(state.data)
  const rows = config.rows ? config.rows(state.data) : isArray ? state.data : state.data?.Items ?? []
  return <>
    <DataError message={state.error} onRetry={() => setVersion((value) => value + 1)} />
    <section className="min-h-[310px] min-w-0 rounded-[14px] border border-admin-border bg-white p-[18px]" aria-label={config.label}>
      <div className="mb-[13px] flex items-center justify-between gap-3"><h3 className="m-0 text-[15px] font-semibold">{config.label}</h3><button type="button" className="cursor-pointer border-0 bg-transparent p-0 text-xs text-admin-red hover:underline" onClick={() => setVersion((value) => value + 1)} disabled={state.loading}>Làm mới</button></div>
      <DataTable columns={config.columns} rows={rows} rowKey={config.rowKey} loading={state.loading} error={state.error} />
      {!isArray && !config.rows && <Pagination page={page} total={state.data?.Total ?? 0} loading={state.loading} onPage={setPage} />}
    </section>
  </>
}

function Reports({ auth }) {
  const [month, setMonth] = useState(currentMonth)
  const [tab, setTab] = useState('orders')
  const configs = {
    orders: { label: 'Thống kê đơn hàng', path: '/admin/statistics/orders', rowKey: 'key', columns: [column('label', 'Trạng thái'), column('value', 'Số đơn')], rows: (data) => data ? Object.entries(data.ByStatus).map(([key, value]) => ({ key, label: ({ Pending: 'Chờ xử lý', Confirmed: 'Đã xác nhận', Shipping: 'Đang giao', Delivered: 'Đã giao', ...STATUS_LABELS })[key] ?? key, value })) : [] },
    revenue: { label: 'Thống kê doanh thu', path: '/admin/statistics/revenue', rowKey: 'key', columns: [column('label', 'Chỉ tiêu'), column('value', 'Giá trị', formatMoney)], rows: (data) => data ? [['CollectedAmount', 'Tiền đã thu'], ['RefundedAmount', 'Tiền đã hoàn'], ['NetRevenue', 'Doanh thu thuần'], ['PendingRefundAmount', 'Tiền chờ hoàn']].map(([key, label]) => ({ key, label, value: data[key] })) : [] },
  }
  return <>
    <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap gap-2">{Object.entries(configs).map(([id, config]) => <button type="button" key={id} className="cursor-pointer rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text aria-pressed:border-admin-blue aria-pressed:bg-admin-soft-blue aria-pressed:text-admin-blue" aria-pressed={tab === id} onClick={() => setTab(id)}>{config.label}</button>)}</div>
      <input type="month" className="max-w-full rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text" aria-label="Tháng báo cáo" value={month} min="2000-01" max={currentMonth()} onChange={(event) => { if (event.target.value) setMonth(event.target.value) }} />
    </div>
    <ListView key={`${tab}-${month}`} auth={auth} config={configs[tab]} params={monthPeriod(month)} />
  </>
}

function Reviews({ auth }) {
  const [page, setPage] = useState(1)
  const [product, setProduct] = useState('')
  const [version, setVersion] = useState(0)
  const state = useAdminData(auth.withAccessToken, '/admin/products', { page, page_size: 20 }, version)
  const config = { label: 'Đánh giá sản phẩm', path: `/admin/products/${product}/reviews`, rowKey: 'ReviewId', columns: [column('User', 'Khách hàng', (user) => user?.FullName ?? '—'), column('Rating', 'Số sao'), column('Content', 'Nội dung'), column('IsDeleted', 'Trạng thái', (value) => value ? 'Đã ẩn' : 'Hiển thị'), column('CreatedAt', 'Ngày đánh giá', formatDate)] }
  return <>
    <DataError message={state.error} onRetry={() => setVersion((value) => value + 1)} />
    <label>Chọn sản phẩm để xem đánh giá <select className="max-w-full rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text" value={product} disabled={state.loading} onChange={(event) => setProduct(event.target.value)}><option value="">Chọn sản phẩm</option>{state.data?.Items.map((item) => <option key={item.ProductId} value={item.ProductId}>{item.Name}</option>)}</select></label>
    <Pagination page={page} total={state.data?.Total ?? 0} loading={state.loading} onPage={(next) => { setProduct(''); setPage(next) }} />
    {product ? <ListView key={product} auth={auth} config={config} /> : <section className="min-h-[310px] min-w-0 rounded-[14px] border border-admin-border bg-white p-[18px]"><DataTable columns={config.columns} rowKey="ReviewId" emptyText={state.loading ? 'Đang tải sản phẩm…' : state.data?.Total ? 'Chọn sản phẩm để xem đánh giá.' : 'Chưa có sản phẩm.'} /></section>}
  </>
}

export default function SectionPage({ section, auth }) {
  const [tab, setTab] = useState(0)
  const support = [{ label: 'Hội thoại', path: auth.user.Role === 'Admin' ? '/admin/conversations' : '/admin/conversations/assigned', rowKey: 'ConversationId', columns: [column('ConversationId', 'Mã hội thoại'), column('Mode', 'Kênh', (value) => value === 'Staff' ? 'Nhân viên' : 'AI'), column('Status', 'Trạng thái', statusLabel), column('CreatedAt', 'Ngày tạo', formatDate)] }]
  const configs = (section.id === 'support' ? support : SECTIONS[section.id] ?? []).filter((config) => !config.permission || auth.permissions.includes(config.permission))
  return <section className="flex flex-col gap-5" aria-label={section.label}>
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="m-0 text-xl font-bold">{section.label}</h2></div>
    {section.id === 'reports' ? <Reports auth={auth} /> : section.id === 'reviews' ? <Reviews auth={auth} /> : <>
      {configs.length > 1 && <div className="flex flex-wrap gap-2">{configs.map((config, index) => <button key={config.path} type="button" className="cursor-pointer rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text aria-pressed:border-admin-blue aria-pressed:bg-admin-soft-blue aria-pressed:text-admin-blue" aria-pressed={tab === index} onClick={() => setTab(index)}>{config.label}</button>)}</div>}
      {configs[tab] && <ListView key={configs[tab].path} auth={auth} config={configs[tab]} />}
    </>}
  </section>
}
