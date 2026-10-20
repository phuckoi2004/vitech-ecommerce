import { useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Button, ErrorState, Spinner } from '../../components/shared/index.js'
import { growth, monthPeriod, recentMonths } from '../../lib/dashboard-periods.js'
import { formatMoney } from '../../lib/format.js'
import { getDashboardStock, getRevenueSeries } from '../../services/api/admin.js'
import warningDot from '../../assets/admin/stock-warning.svg'
import AdminTable, { AdminPanel, ORDER_COLUMNS } from '../components/AdminTable.jsx'
import RevenueChart from '../components/RevenueChart.jsx'
import useAdminQuery, { useAdminLoad } from '../hooks/useAdminQuery.js'
import useBrowserMonth from '../hooks/useBrowserMonth.js'

const STOCK_COLUMNS = [
  { key: 'ProductName', label: 'Sản phẩm', render: (value, row) => <span className="flex flex-col gap-1"><strong className="font-medium">{value}</strong><small className="text-[10px] text-admin-muted">{row.VariantName} · {row.Sku}</small></span> },
  { key: 'StockQuantity', label: 'Tồn kho', className: 'w-[112px]', render: (value) => <span className="flex items-center justify-between gap-2 font-semibold text-admin-red">{value}<img src={warningDot} width="10" height="10" className="shrink-0" alt="Tồn kho thấp" /></span> },
]

function StatCard({ label, value, loading, error, note, tone = '' }) {
  return <article aria-label={label} aria-busy={loading} className="flex min-h-[132px] min-w-0 flex-col gap-2 rounded-[14px] border border-admin-border bg-white px-5 py-[18px] max-[480px]:p-4">
    <h3 className="text-[13px] font-medium text-admin-muted">{label}</h3>
    <strong className={`${String(value).length > 15 ? 'text-[20px]' : 'text-[28px]'} leading-[1.2] font-bold whitespace-nowrap`}>{loading ? <span className="flex h-[34px] items-center gap-2 text-sm text-admin-muted"><Spinner />Đang tải…</span> : error ? '—' : value}</strong>
    {note && !loading && !error && <p className={`text-xs font-medium ${tone || 'text-admin-muted'}`}>{note}</p>}
  </article>
}

function GrowthNote({ current, previous }) {
  const percent = growth(current, previous)
  if (percent === null) return null
  return <span className={percent < 0 ? 'text-admin-red' : 'text-[#16a34a]'}>{percent >= 0 ? '+' : ''}{percent.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}% so với tháng trước</span>
}

export default function DashboardPage() {
  const month = useBrowserMonth()
  const months = useMemo(() => recentMonths(month), [month])
  const orders = useAdminQuery('/admin/statistics/orders', monthPeriod(month))
  const previousOrders = useAdminQuery('/admin/statistics/orders', monthPeriod(months[3]))
  const pending = useAdminQuery('/admin/orders', { order_status: 'Pending', page: 1, page_size: 1 })
  const latest = useAdminQuery('/admin/orders', { page: 1, page_size: 4 })
  const stock = useAdminLoad(getDashboardStock)
  const loadRevenue = useCallback((token, signal) => getRevenueSeries(token, months, signal), [months])
  const revenue = useAdminLoad(loadRevenue)
  const currentRevenue = revenue.data?.find((point) => point.month === month)
  const previousRevenue = revenue.data?.find((point) => point.month === months[3])
  const summaryError = orders.error || pending.error || stock.error || revenue.error || currentRevenue?.error || previousOrders.error || previousRevenue?.error
  const refresh = () => [orders, previousOrders, pending, latest, stock, revenue].forEach((state) => state.refresh())

  return <section aria-labelledby="dashboard-heading" className="flex min-w-0 flex-col gap-[22px]">
    <div className="flex items-center justify-between gap-4"><h2 id="dashboard-heading" className="text-xl leading-6 font-bold">Tổng quan hoạt động</h2>
      <Button variant="ghost" size="sm" className="h-6! px-2! text-[11px]!" onClick={refresh} disabled={[orders, pending, stock, revenue].some((state) => state.loading)}>Làm mới</Button>
    </div>
    {summaryError && <ErrorState title="Một số thống kê chưa tải được" message={summaryError} onRetry={refresh} className="w-full max-w-none py-4" />}
    <div className="grid grid-cols-4 gap-4 max-[1400px]:grid-cols-2 max-[600px]:grid-cols-1 max-[480px]:gap-3">
      <StatCard label="Tổng đơn hàng" value={(orders.data?.TotalOrders ?? 0).toLocaleString('vi-VN')} loading={orders.loading} error={orders.error} note={<GrowthNote current={orders.data?.TotalOrders} previous={previousOrders.data?.TotalOrders} />} />
      <StatCard label="Doanh thu" value={formatMoney(currentRevenue?.data?.NetRevenue ?? 0)} loading={revenue.loading} error={revenue.error || currentRevenue?.error} note={<GrowthNote current={currentRevenue?.data?.NetRevenue} previous={previousRevenue?.data?.NetRevenue} />} />
      <StatCard label="Đơn chờ xử lý" value={(pending.data?.Total ?? 0).toLocaleString('vi-VN')} loading={pending.loading} error={pending.error} note={pending.data?.Total > 0 ? 'Cần xử lý đơn hàng' : null} tone="text-[#f59e0b]" />
      <StatCard label="Sản phẩm sắp hết" value={(stock.data?.Total ?? 0).toLocaleString('vi-VN')} loading={stock.loading} error={stock.error} note={stock.data?.Total > 0 ? 'Cần kiểm tra tồn kho' : null} tone="text-admin-red" />
    </div>
    <RevenueChart months={months} state={revenue} />
    <div className="grid grid-cols-[minmax(0,1fr)_350px] gap-[18px] max-[1200px]:grid-cols-[minmax(0,1.8fr)_minmax(260px,1fr)] max-[1050px]:grid-cols-1">
      <AdminPanel title="Đơn hàng mới nhất" className="min-h-[310px]" action={<Link className="text-xs font-semibold text-admin-red hover:underline" to="/admin/orders">Xem tất cả</Link>}>
        <AdminTable label="Đơn hàng mới nhất" columns={ORDER_COLUMNS} rows={latest.data?.Items} rowKey="OrderId" loading={latest.loading} error={latest.error} onRetry={latest.refresh} emptyText="Chưa có đơn hàng." className="min-w-[590px]" />
      </AdminPanel>
      <AdminPanel title="Cảnh báo tồn kho" className="min-h-[310px]">
        <p className="mb-3.5 text-[11px] text-admin-muted">Các sản phẩm cần nhập thêm</p>
        <AdminTable label="Cảnh báo tồn kho" columns={STOCK_COLUMNS} rows={stock.data?.Items} rowKey="ProductVariantId" loading={stock.loading} error={stock.error} onRetry={stock.refresh} emptyText="Chưa có sản phẩm cần cảnh báo." className="admin-table--dashboard-stock" />
        {stock.data?.Total > 4 && <Link className="mt-3 inline-block text-xs text-admin-red hover:underline" to="/admin/inventory?tab=low-stock">Xem tất cả ({stock.data.Total})</Link>}
      </AdminPanel>
    </div>
  </section>
}
