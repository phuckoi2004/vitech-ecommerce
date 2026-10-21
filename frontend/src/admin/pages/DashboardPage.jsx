import { useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ErrorState } from '../../components/shared/index.js'
import { growth, monthToDate, previousMonthToDate, recentMonths } from '../../lib/dashboard-periods.js'
import { formatMoney } from '../../lib/format.js'
import { getDashboardStock, getRevenueSeries } from '../../services/api/admin.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import AdminTable, { AdminPanel, ORDER_COLUMNS } from '../components/AdminTable.jsx'
import RevenueChart from '../components/RevenueChart.jsx'
import useDashboardQuery, { useDashboardLoad } from '../hooks/useDashboardQuery.js'
import ReportMetric from '../components/ReportMetric.jsx'
import useReportingDate from '../hooks/useReportingDate.js'
import { reportMargin, reportRangeLabel } from '../lib/reports.js'
import '../components/Reports.css'

const STOCK_COLUMNS = [
  { key: 'ProductName', label: 'Sản phẩm / SKU', render: (value, row) => <span className="flex flex-col gap-1"><Link className="font-medium text-admin-blue hover:underline" to={'/admin/products?dialog=view&variant=' + encodeURIComponent(row.ProductVariantId)}>{value}</Link><small className="text-xs text-admin-muted">{row.VariantName} · {row.Sku}</small></span> },
  { key: 'StockQuantity', label: 'Tồn kho khả dụng', className: 'w-[144px] text-center tabular-nums', render: (value) => <span className={'font-semibold ' + (value === 0 ? 'text-admin-red' : 'text-amber-700')}>{value}</span> },
]
function StatCard({ label, value, money, loading, error, note, negative = false }) {
  return <article aria-label={label} aria-busy={loading} className="report-metric-card flex min-h-[146px] min-w-0 flex-col gap-2 rounded-[14px] border border-admin-border bg-white p-5">
    <h3 className="m-0 text-sm font-medium text-admin-muted">{label}</h3>
    <strong className={'report-metric-value leading-tight font-bold tabular-nums wrap-anywhere ' + (negative ? 'text-admin-red ' : '') + (value === 'Chưa đủ dữ liệu' ? 'text-lg text-admin-muted' : 'text-[28px]')}>{loading || error ? '—' : <ReportMetric value={value} money={money} />}</strong>
    {!loading && !error && <div className="mt-auto text-xs text-admin-muted">{note}</div>}
  </article>
}
function GrowthNote({ current, previous }) {
  const percent = growth(current, previous)
  return percent === null ? <span>Chưa có cơ sở so sánh cùng kỳ</span> : <span className={percent < 0 ? 'text-admin-red' : percent > 0 ? 'text-[#15803d]' : ''}>{percent > 0 ? '+' : ''}{percent.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}% so với cùng kỳ tháng trước</span>
}
export default function DashboardPage() {
  const { permissions } = useInternalAuth(), today = useReportingDate(), month = today.slice(0, 7)
  const can = (name) => permissions.includes(name + ':view')
  const months = useMemo(() => recentMonths(month, 6), [month])
  const period = monthToDate(today), previousPeriod = previousMonthToDate(today)
  const current = useDashboardQuery('/admin/statistics/reports/revenue', { ...period, page: 1, page_size: 1 }, can('revenue_reports'), 0)
  const previous = useDashboardQuery('/admin/statistics/reports/revenue', { ...previousPeriod, page: 1, page_size: 1 }, can('revenue_reports'), 0)
  const orders = useDashboardQuery('/admin/statistics/reports/orders', { ...period, page: 1, page_size: 1 }, can('order_reports'), 0)
  const workload = useDashboardQuery('/admin/statistics/workload')
  const latest = useDashboardQuery('/admin/orders', { page: 1, page_size: 5 }, can('orders'))
  const stock = useDashboardLoad(getDashboardStock, can('inventory') && can('products'))
  const loadRevenue = useCallback((token, signal) => getRevenueSeries(token, months, signal, today), [months, today])
  const revenue = useDashboardLoad(loadRevenue, can('revenue_reports'), 0)
  const states = [current, previous, orders, workload, latest, stock, revenue]
  const refresh = () => states.forEach((state) => state.refresh())
  const error = states.find((state) => state.error)?.error
  const summary = current.data?.Summary, before = previous.data?.Summary
  const orderSummary = orders.data?.Summary, totalOrders = (orderSummary?.TotalOrders ?? 0).toLocaleString('vi-VN')
  const deliveredOrders = (orderSummary?.DeliveredOrders ?? 0).toLocaleString('vi-VN')
  const cancelledOrders = (orderSummary?.CancelledOrders ?? 0).toLocaleString('vi-VN')
  const tasks = [
    ['orders', 'Chờ xác nhận', workload.data?.PendingOrders, '/admin/orders?status=Pending'],
    ['chat', 'Chat đang chờ', workload.data?.WaitingChats, '/admin/support?tab=waiting'],
    ['returns', 'Đổi trả đang chờ', workload.data?.PendingReturns, '/admin/returns?status=Pending'],
    ['warranties', 'Bảo hành mới', workload.data?.NewWarranties, '/admin/warranties?status=New'],
  ].filter(([permission]) => can(permission))
  const updates = states.map((state) => state.updatedAt).filter(Boolean)
  return <section aria-labelledby="dashboard-heading" className="flex min-w-0 flex-col gap-5">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="dashboard-heading" className="m-0 text-xl font-bold">Tổng quan hoạt động</h2><p className="mt-1 mb-0 text-xs text-admin-muted">{updates.length ? 'Có dữ liệu cập nhật lúc ' + new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' }).format(new Date(Math.max(...updates))) + ' · Múi giờ GMT+7' : 'Đang tải dữ liệu…'}</p></div><button type="button" className="report-button" onClick={refresh} disabled={states.some((s) => s.loading || s.refreshing)}>Làm mới</button></header>
    {error && <ErrorState title="Một số dữ liệu chưa tải được" message={error} onRetry={refresh} className="w-full max-w-none py-4" />}
    {!!tasks.length && <section aria-label="Việc cần xử lý hiện tại"><div className="grid grid-cols-4 gap-3 max-[1200px]:grid-cols-2">{tasks.map(([key, label, value, href]) => <Link key={key} to={href} aria-label={label} className="flex min-w-0 items-center justify-between gap-3 rounded-xl border border-admin-border bg-white p-4 text-sm text-admin-text transition-colors hover:border-admin-blue hover:bg-admin-soft"><span>{label}</span><strong className={'text-xl tabular-nums ' + (Number(value) > 0 ? 'text-amber-700' : 'text-admin-muted')}>{workload.loading || workload.error ? '—' : (value ?? 0).toLocaleString('vi-VN')}</strong></Link>)}</div></section>}
    <div><h3 className="mt-0 mb-1 text-sm font-semibold">Tháng này, tính đến hôm nay</h3><p className="mt-0 mb-3 text-xs text-admin-muted">{reportRangeLabel(period.date_from, period.date_to)} · So sánh {reportRangeLabel(previousPeriod.date_from, previousPeriod.date_to)}</p>
      <div className="report-metrics grid grid-cols-4 gap-4 max-[1200px]:grid-cols-2">
        {can('revenue_reports') && <><StatCard label="Doanh số bán hàng" money={summary?.Revenue} value={formatMoney(summary?.Revenue ?? 0)} loading={current.loading} error={current.error} note={<><GrowthNote current={summary?.Revenue} previous={before?.Revenue} /><p className="mt-1 mb-0">Sau giảm giá · Không gồm phí ship</p></>} />
        <StatCard label="Lãi gộp" money={summary?.Profit} negative={Number(summary?.Profit) < 0} value={summary?.Profit == null ? 'Chưa đủ dữ liệu' : formatMoney(summary.Profit)} loading={current.loading} error={current.error} note={<>{summary?.LinesMissingCost ? summary.LinesMissingCost + ' dòng chưa có giá nhập' : 'Biên lãi ' + reportMargin(summary?.Margin)}<p className="mt-1 mb-0">Trước điều chỉnh trả hàng</p></>} /></>}
        {can('order_reports') && <>
          <StatCard label="Số đơn đã giao" value={deliveredOrders} loading={orders.loading} error={orders.error} note={<><span>{deliveredOrders} / {totalOrders}</span><p className="mt-1 mb-0">Tính trên các đơn đặt trong kỳ</p></>} />
          <StatCard label="Số đơn hủy" value={cancelledOrders} loading={orders.loading} error={orders.error} note={<><span>{cancelledOrders} / {totalOrders}</span><p className="mt-1 mb-0">Tính trên các đơn đặt trong kỳ</p></>} />
        </>}
      </div>
    </div>
    {can('revenue_reports') && <RevenueChart months={months} state={revenue} today={today} />}
    <div className="grid grid-cols-[minmax(0,2fr)_minmax(280px,1fr)] gap-5 max-[1200px]:grid-cols-1">
      {can('orders') && <AdminPanel title="Đơn hàng mới nhất" action={<Link className="text-sm font-semibold text-admin-blue hover:underline" to="/admin/orders">Xem tất cả</Link>}><AdminTable label="Đơn hàng mới nhất" columns={ORDER_COLUMNS} rows={latest.data?.Items} rowKey="OrderId" loading={latest.loading} error={latest.error} onRetry={latest.refresh} emptyText="Chưa có đơn hàng." /></AdminPanel>}
      {can('inventory') && can('products') && <AdminPanel title="Cảnh báo tồn kho"><p className="mt-0 mb-3 text-xs text-admin-muted">Biến thể đang bán · Hết hàng hoặc sắp hết</p><div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs"><Link aria-label="Hết hàng" className="text-admin-red hover:underline" to="/admin/products?status=Active&stock=out_of_stock">Hết hàng: {stock.loading || stock.error ? '—' : stock.data?.OutOfStockTotal ?? 0}</Link><Link aria-label="Sắp hết" className="text-amber-700 hover:underline" to="/admin/products?status=Active&stock=low_stock">Sắp hết: {stock.loading || stock.error ? '—' : stock.data?.LowStockTotal ?? 0}</Link></div><AdminTable label="Cảnh báo tồn kho" columns={STOCK_COLUMNS} rows={stock.data?.Items} rowKey="ProductVariantId" loading={stock.loading} error={stock.error} onRetry={stock.refresh} emptyText="Chưa có sản phẩm cần cảnh báo." className="admin-table--dashboard-stock" /></AdminPanel>}
    </div>
  </section>
}
