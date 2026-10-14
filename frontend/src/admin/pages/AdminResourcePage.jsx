import { useState } from 'react'
import { browserMonth as currentMonth, monthPeriod } from '../../lib/dashboard-periods.js'
import { formatDate, formatMoney } from '../../lib/format.js'
import { Pagination as SharedPagination } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { useSearchParams } from 'react-router-dom'
import useAdminQuery from '../hooks/useAdminQuery.js'
import DataTable from '../components/AdminTable.jsx'

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
  promotions: [{ label: 'Khuyến mãi', path: '/admin/promotions', rowKey: 'PromotionId', columns: [column('Name', 'Chương trình'), column('Status', 'Trạng thái', statusLabel), column('StartDate', 'Bắt đầu', formatDate), column('EndDate', 'Kết thúc', formatDate)] }],
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
  return <div className="mt-[18px]"><SharedPagination page={page} total={total} pageSize={pageSize} disabled={loading} onPageChange={onPage} /></div>
}

function ListView({ config, params = {} }) {
  const [page, setPage] = useState(1)
  const state = useAdminQuery(config.path, { page, page_size: 20, ...config.params, ...params })
  const isArray = Array.isArray(state.data)
  const rows = config.rows ? config.rows(state.data) : isArray ? state.data : state.data?.Items ?? []
  return <>
    <section className="min-h-[310px] min-w-0 rounded-[14px] border border-admin-border bg-white p-[18px]" aria-label={config.label}>
      <div className="mb-[13px] flex items-center justify-between gap-3"><h3 className="m-0 text-[15px] font-semibold">{config.label}</h3><button type="button" className="cursor-pointer border-0 bg-transparent p-0 text-xs text-admin-red hover:underline" onClick={state.refresh} disabled={state.loading}>Làm mới</button></div>
      <DataTable columns={config.columns} rows={rows} rowKey={config.rowKey} loading={state.loading} error={state.error} onRetry={state.refresh} />
      {!isArray && !config.rows && <Pagination page={page} total={state.data?.Total ?? 0} loading={state.loading} onPage={setPage} />}
    </section>
  </>
}

function Reports() {
  const [month, setMonth] = useState(currentMonth)
  const [tab, setTab] = useState('orders')
  const configs = {
    orders: { label: 'Thống kê đơn hàng', path: '/admin/statistics/orders', rowKey: 'key', columns: [column('label', 'Trạng thái'), column('value', 'Số đơn')], rows: (data) => data ? Object.entries(data.ByStatus).map(([key, value]) => ({ key, label: ({ Pending: 'Chờ xử lý', Confirmed: 'Đã xác nhận', Shipping: 'Đang giao', Delivered: 'Đã giao', ...STATUS_LABELS })[key] ?? key, value })) : [] },
    revenue: { label: 'Thống kê doanh thu', path: '/admin/statistics/revenue', rowKey: 'key', columns: [column('label', 'Chỉ tiêu'), column('value', 'Giá trị', formatMoney)], rows: (data) => data ? [['CollectedAmount', 'Tiền đã thu'], ['RefundedAmount', 'Tiền đã hoàn'], ['NetRevenue', 'Doanh thu thuần'], ['PendingRefundAmount', 'Tiền chờ hoàn']].map(([key, label]) => ({ key, label, value: data[key] })) : [] },
  }
  return <>
    <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap gap-2">{Object.entries(configs).map(([id, config]) => <button type="button" key={id} className="cursor-pointer rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text aria-pressed:border-admin-blue aria-pressed:bg-admin-soft aria-pressed:text-admin-blue" aria-pressed={tab === id} onClick={() => setTab(id)}>{config.label}</button>)}</div>
      <input type="month" className="max-w-full rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text" aria-label="Tháng báo cáo" value={month} min="2000-01" max={currentMonth()} onChange={(event) => { if (event.target.value) setMonth(event.target.value) }} />
    </div>
    <ListView key={`${tab}-${month}`} config={configs[tab]} params={monthPeriod(month)} />
  </>
}

export default function AdminResourcePage({ section }) {
  const auth = useInternalAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const secondTab = section.id === 'inventory' ? 'low-stock' : '1'
  function setTab(index) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      if (index === 0) next.delete('tab')
      else next.set('tab', secondTab)
      return next
    })
  }
  const support = [{ label: 'Hội thoại', path: auth.user.Role === 'Admin' ? '/admin/conversations' : '/admin/conversations/assigned', rowKey: 'ConversationId', columns: [column('ConversationId', 'Mã hội thoại'), column('Mode', 'Kênh', (value) => value === 'Staff' ? 'Nhân viên' : 'AI'), column('Status', 'Trạng thái', statusLabel), column('CreatedAt', 'Ngày tạo', formatDate)] }]
  const configs = (section.id === 'support' ? support : SECTIONS[section.id] ?? []).filter((config) => !config.permission || auth.permissions.includes(config.permission))
  const tab = configs.length > 1 && searchParams.get('tab') === secondTab ? 1 : 0
  return <section className="flex flex-col gap-5" aria-label={section.label}>
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="m-0 text-xl font-bold">{section.label}</h2></div>
    {section.id === 'reports' ? <Reports /> : <>
      {configs.length > 1 && <div className="flex flex-wrap gap-2">{configs.map((config, index) => <button key={config.path} type="button" className="cursor-pointer rounded-lg border border-admin-border bg-white px-3 py-2 text-[13px] text-admin-text aria-pressed:border-admin-blue aria-pressed:bg-admin-soft aria-pressed:text-admin-blue" aria-pressed={tab === index} onClick={() => setTab(index)}>{config.label}</button>)}</div>}
      {configs[tab] && <ListView key={configs[tab].path} config={configs[tab]} />}
    </>}
  </section>
}
