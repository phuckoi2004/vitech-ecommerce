import { formatMoney } from '../../lib/format.js'
import { reportMargin, reportRate } from '../lib/reports.js'
import ReportMetric from './ReportMetric.jsx'

const reportMoney = (value) => value == null ? 'Chưa đủ dữ liệu' : formatMoney(value)
export default function ReportSummary({ tab, data, loading, error, filtered = false, onCancelled, cancelledOpen = false, onDelivered, deliveredOpen = false }) {
  const total = data?.TotalOrders ?? 0
  const cards = tab === 'revenue' ? [
    ['Doanh số bán hàng', reportMoney(data?.Revenue), 'Sau giảm giá · Không gồm phí ship'],
    ['Tổng giá nhập', reportMoney(data?.Cost), data?.LinesMissingCost ? data.LinesMissingCost + ' dòng chưa có giá nhập' : 'Giá nhập đã lưu trên đơn'],
    ['Lãi gộp', reportMoney(data?.Profit), 'Biên lãi ' + reportMargin(data?.Margin) + ' · Trước điều chỉnh trả hàng'],
    ['Đơn ghi nhận bán hàng', total.toLocaleString('vi-VN'), (filtered ? 'Doanh số SP đã chọn / đơn: ' : 'Trung bình / đơn: ') + formatMoney(data?.AverageOrderValue ?? 0)],
  ] : [
    ['Đơn đặt trong kỳ', total.toLocaleString('vi-VN'), 'Theo ngày đặt hàng'],
    ['Đang xử lý', (data?.InProgressOrders ?? 0).toLocaleString('vi-VN'), 'Chờ xác nhận, xử lý hoặc đang giao'],
    ['Đã giao', (data?.DeliveredOrders ?? 0).toLocaleString('vi-VN'), reportRate(data?.DeliveredOrders ?? 0, total) + ' số đơn đặt trong kỳ', 'delivered'],
    ['Đã hủy', (data?.CancelledOrders ?? 0).toLocaleString('vi-VN'), 'Tỷ lệ hủy ' + reportRate(data?.CancelledOrders ?? 0, total), 'cancelled'],
  ]
  return <div aria-label="Tổng hợp báo cáo" aria-busy={loading} className="report-metrics grid grid-cols-4 gap-4 max-[1200px]:grid-cols-2">{cards.map(([label, value, note, action]) => {
    const onAction = action === 'cancelled' ? onCancelled : action === 'delivered' ? onDelivered : null
    const expanded = action === 'cancelled' ? cancelledOpen : deliveredOpen
    const actionable = !!onAction
    return <article key={label} aria-label={label} className={'report-metric-card relative flex min-h-[142px] min-w-0 flex-col gap-2 rounded-[14px] border p-5 ' + (actionable && expanded ? 'border-admin-blue bg-admin-soft' : 'border-admin-border bg-white') + (actionable ? ' transition-colors hover:border-admin-blue' : '')}>
      <h3 className="m-0 text-sm font-medium text-admin-muted">{label}</h3>
      <p className={'report-metric-value m-0 leading-tight font-bold tabular-nums wrap-anywhere ' + (label === 'Lãi gộp' && Number(data?.Profit) < 0 ? 'text-admin-red ' : '') + (value === 'Chưa đủ dữ liệu' ? 'text-lg text-admin-muted' : 'text-[26px]')}>{loading || error ? '—' : <ReportMetric value={value} money={label === 'Doanh số bán hàng' ? data?.Revenue : label === 'Tổng giá nhập' ? data?.Cost : label === 'Lãi gộp' ? data?.Profit : undefined} />}</p>
      <p className="mt-auto mb-0 text-xs text-admin-muted">{note}</p>
      {actionable && <><span aria-hidden="true" className="text-xs font-semibold text-admin-blue">{expanded ? 'Ẩn danh sách' : 'Xem danh sách'}</span><button id={'report-' + action + '-trigger'} type="button" aria-label={(expanded ? 'Ẩn' : 'Xem') + ' danh sách đơn ' + label.toLocaleLowerCase('vi-VN')} aria-expanded={expanded} aria-controls={'report-' + action + '-orders'} disabled={loading || !!error || !data} onClick={onAction} className="absolute inset-0 cursor-pointer rounded-[14px] border-0 bg-transparent disabled:cursor-default" /></>}
    </article>
  })}</div>
}
