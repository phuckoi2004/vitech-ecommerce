import { formatMoney } from '../../lib/format.js'
import { reportRate } from '../lib/reports.js'

export default function ReportSummary({ tab, data, loading, error }) {
  const total = data?.TotalOrders ?? 0, delivered = data?.DeliveredOrders ?? 0, cancelled = data?.CancelledOrders ?? 0
  const money = (value) => formatMoney(value ?? 0)
  const cards = tab === 'revenue' ? [
    ['Tổng doanh thu', money(data?.Revenue), 'Trong kỳ đã chọn'],
    ['Tổng đơn hàng', `${total.toLocaleString('vi-VN')} đơn`, 'Dữ liệu bán hàng'],
    ['Giá trị trung bình / đơn', money(data?.AverageOrderValue), 'Doanh thu / tổng đơn'],
    ['Doanh thu cao nhất', money(data?.PeakRevenue), 'Mốc cao nhất trong kỳ'],
  ] : [
    ['Tổng số đơn hàng', `${total.toLocaleString('vi-VN')} đơn`, 'Trong kỳ đã chọn'],
    ['Giao thành công', `${delivered.toLocaleString('vi-VN')} đơn`, 'Tỷ lệ ' + reportRate(delivered, total)],
    ['Đã hủy', `${cancelled.toLocaleString('vi-VN')} đơn`, 'Tỷ lệ ' + reportRate(cancelled, total)],
    ['Tỷ lệ giao thành công', reportRate(delivered, total), 'So với tổng số đơn'],
  ]
  return <div aria-label="Tổng hợp báo cáo" aria-busy={loading} className="grid grid-cols-4 gap-4 max-[1100px]:grid-cols-2 max-[480px]:grid-cols-1">{cards.map(([label, value, note]) => <section key={label} aria-label={label} className="flex min-h-[132px] min-w-0 flex-col gap-2 rounded-[14px] border border-admin-border bg-white p-5"><h3 className="m-0 text-sm font-medium text-admin-muted">{label}</h3><p className="m-0 text-[24px] leading-tight font-bold wrap-anywhere" title={value}>{loading || error ? '—' : value}</p><p className="m-0 text-xs text-admin-muted">{note}</p></section>)}</div>
}
