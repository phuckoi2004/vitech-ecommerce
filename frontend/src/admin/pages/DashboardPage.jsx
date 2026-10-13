import { useEffect, useState } from 'react'
import { currentMonth, getLowStock, getOrderStatistics, getRecentOrders, getRevenueStatistics } from '../../lib/admin-dashboard-api.js'
import DataTable, { DataError, formatMoney, ORDER_COLUMNS } from '../components/DataTable.jsx'

const EMPTY = { data: null, loading: true, error: '' }
const STOCK_COLUMNS = [
  { key: 'ProductName', label: 'Sản phẩm / Biến thể', render: (name, row) => <span className="flex flex-col gap-1"><strong className="font-medium">{name}</strong><small className="text-[10px] text-admin-muted">{row.Sku}</small></span> },
  { key: 'StockQuantity', label: 'Tồn kho', render: (value) => <span className="text-admin-red">{value}</span> },
]

function StatCard({ label, state, value, hint, tone = '' }) {
  const hintColor = { warning: 'text-admin-warning', danger: 'text-admin-red' }[tone] ?? 'text-admin-muted'
  return <article className="flex min-h-[132px] flex-col gap-2 rounded-[14px] border border-admin-border bg-white px-5 py-[18px] max-[480px]:p-4" aria-busy={state.loading}>
    <h3 className="m-0 text-[13px] font-normal text-admin-muted">{label}</h3>
    <strong className="dashboard-stat-value text-[clamp(24px,2.1vw,30px)] leading-[1.2] font-bold wrap-anywhere max-[480px]:text-[24px]">{state.error ? '—' : state.loading ? '…' : value}</strong>
    <p className={`m-0 text-xs leading-normal ${hintColor}`}>{state.error ? 'Không tải được dữ liệu' : hint}</p>
  </article>
}

export default function DashboardPage({ auth, onSelect }) {
  const [month, setMonth] = useState(currentMonth)
  const [version, setVersion] = useState(0)
  const [states, setStates] = useState({ orders: EMPTY, revenue: EMPTY, recent: EMPTY, stock: EMPTY })
  const { withAccessToken } = auth
  useEffect(() => {
    const controller = new AbortController()
    const requests = { orders: getOrderStatistics, revenue: getRevenueStatistics, recent: getRecentOrders, stock: getLowStock }
    setStates({ orders: EMPTY, revenue: EMPTY, recent: EMPTY, stock: EMPTY })
    for (const [key, read] of Object.entries(requests)) {
      withAccessToken((token) => key === 'orders' || key === 'revenue' ? read(token, month, controller.signal) : read(token, controller.signal))
        .then((data) => { if (!controller.signal.aborted) setStates((previous) => ({ ...previous, [key]: { data, loading: false, error: '' } })) })
        .catch((failure) => { if (!controller.signal.aborted) setStates((previous) => ({ ...previous, [key]: { data: null, loading: false, error: failure.message } })) })
    }
    return () => controller.abort()
  }, [withAccessToken, month, version])

  const retry = () => setVersion((value) => value + 1)
  const errors = [...new Set(Object.values(states).map((state) => state.error).filter(Boolean))].join(' ')

  return <section className="flex flex-col gap-[22px]" aria-labelledby="dashboard-heading">
    <div className="flex min-h-8 items-center justify-between gap-4 max-[480px]:flex-col max-[480px]:items-start">
      <h2 id="dashboard-heading" className="m-0 text-xl leading-[1.4] font-bold">Tổng quan hoạt động</h2>
      <label className="relative flex items-center gap-2.5 rounded-[10px] border border-admin-border bg-white px-3 py-2 text-xs whitespace-nowrap text-admin-muted"><span>Tháng {Number(month.slice(5))} / {month.slice(0, 4)}</span><input type="month" className="w-[22px] min-w-[22px] border-0 bg-transparent text-transparent [&::-webkit-calendar-picker-indicator]:m-0 [&::-webkit-calendar-picker-indicator]:cursor-pointer [&::-webkit-calendar-picker-indicator]:opacity-65 [&::-webkit-datetime-edit]:hidden" aria-label="Tháng thống kê" value={month} min="2000-01" max={currentMonth()} onChange={(event) => { if (event.target.value) setMonth(event.target.value) }} /></label>
    </div>
    <DataError message={errors} onRetry={retry} />
    <div className="grid grid-cols-4 gap-4 max-[1050px]:grid-cols-2 max-[480px]:gap-3">
      <StatCard label="Tổng đơn hàng" state={states.orders} value={(states.orders.data?.TotalOrders ?? 0).toLocaleString('vi-VN')} hint="Đơn hàng trong tháng" />
      <StatCard label="Doanh thu" state={states.revenue} value={formatMoney(states.revenue.data?.NetRevenue)} hint="Doanh thu thuần trong tháng" />
      <StatCard label="Đơn chờ xử lý" state={states.orders} value={(states.orders.data?.ByStatus?.Pending ?? 0).toLocaleString('vi-VN')} hint="Đơn chờ xử lý trong tháng" tone="warning" />
      <StatCard label="Sản phẩm sắp hết" state={states.stock} value={(states.stock.data?.Total ?? 0).toLocaleString('vi-VN')} hint="Biến thể cần kiểm tra tồn kho" tone="danger" />
    </div>
    <div className="grid grid-cols-[minmax(0,1fr)_350px] gap-[18px] max-[1200px]:grid-cols-[minmax(0,1.8fr)_minmax(260px,1fr)] max-[1050px]:grid-cols-1">
      <section className="min-h-[310px] min-w-0 rounded-[14px] border border-admin-border bg-white p-[18px]" aria-labelledby="recent-orders-heading">
        <div className="mb-[13px] flex items-center justify-between gap-3"><h3 id="recent-orders-heading" className="m-0 text-[15px] font-semibold">Đơn hàng mới nhất</h3><button type="button" className="cursor-pointer border-0 bg-transparent p-0 text-xs text-admin-red hover:underline" onClick={() => onSelect('orders')}>Xem tất cả</button></div>
        <DataTable className="min-w-[590px]" columns={ORDER_COLUMNS} rows={states.recent.data?.Items ?? []} rowKey="OrderId" loading={states.recent.loading} error={states.recent.error} emptyText="Chưa có đơn hàng." />
      </section>
      <section className="min-h-[310px] min-w-0 rounded-[14px] border border-admin-border bg-white p-[18px]" aria-labelledby="low-stock-heading">
        <div className="mb-[13px] flex items-center justify-between gap-3"><h3 id="low-stock-heading" className="m-0 text-[15px] font-semibold">Cảnh báo tồn kho</h3></div>
        <p className="m-0 mb-3.5 text-[11px] text-admin-muted">Các sản phẩm cần nhập thêm</p>
        <DataTable columns={STOCK_COLUMNS} rows={states.stock.data?.Items ?? []} rowKey="ProductVariantId" loading={states.stock.loading} error={states.stock.error} emptyText="Chưa có sản phẩm cần cảnh báo." />
        {!states.stock.loading && !states.stock.error && states.stock.data?.Total > 4 && <button type="button" className="cursor-pointer border-0 bg-transparent p-0 text-xs text-admin-red hover:underline" onClick={() => onSelect('inventory')}>Xem tất cả ({states.stock.data.Total})</button>}
      </section>
    </div>
  </section>
}
