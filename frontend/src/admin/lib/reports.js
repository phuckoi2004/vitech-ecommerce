import { browserMonth, monthPeriod, recentMonths, vietnamToday } from '../../lib/dashboard-periods.js'
import { formatDate } from '../../lib/format.js'

export const REPORT_TABS = { revenue: 'Bán hàng & lãi gộp', orders: 'Đơn hàng' }
export const REPORT_PAGE_SIZE = 10
export const REPORT_SORTS = ['revenue', 'quantity', 'cost', 'profit', 'margin', 'name'].flatMap((key) => [key + '_asc', key + '_desc'])
const validMonth = (value) => /^\d{4}-(0[1-9]|1[0-2])$/.test(value ?? '')
export const validReportDay = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value ?? '') && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value

export function reportPeriods() {
  return [['month', 'Theo tháng'], ['quarter', 'Theo quý'], ['year', 'Theo năm'], ['recent', '6 tháng gần nhất'], ['custom', 'Khoảng ngày']]
}
export function defaultReportFilters(now = new Date()) {
  const month = browserMonth(now)
  return { period: 'month', month, year: month.slice(0, 4), quarter: String(Math.ceil(Number(month.slice(5)) / 3)),
    date_from: month + '-01', date_to: vietnamToday(now), category_id: '', brand_id: '', product_id: '', sort: 'revenue_desc' }
}
export function reportFilters(params, now = new Date()) {
  const result = defaultReportFilters(now)
  for (const key of Object.keys(result)) if (params.has(key)) result[key] = params.get(key)
  // Links from the dashboard can select a calendar month directly.
  if (validMonth(result.period)) { result.month = result.period; result.period = 'month' }
  if (!reportPeriods().some(([key]) => key === result.period)) result.period = 'month'
  if (!validMonth(result.month)) result.month = browserMonth(now)
  if (!REPORT_SORTS.includes(result.sort)) result.sort = 'revenue_desc'
  return result
}
export function reportPeriod(filter, now = new Date()) {
  const today = vietnamToday(now), current = today.slice(0, 7)
  let from, to
  if (filter.period === 'custom') { from = filter.date_from; to = filter.date_to }
  else if (filter.period === 'quarter' || filter.period === 'year') {
    const year = Number(filter.year), quarter = Number(filter.quarter)
    if (!Number.isInteger(year) || year < 1900 || year > 9998 || (filter.period === 'quarter' && ![1, 2, 3, 4].includes(quarter))) throw new Error('Vui lòng chọn năm và quý hợp lệ.')
    const first = filter.period === 'year' ? 1 : (quarter - 1) * 3 + 1
    const last = filter.period === 'year' ? 12 : first + 2
    from = `${year}-${String(first).padStart(2, '0')}-01`
    to = monthPeriod(`${year}-${String(last).padStart(2, '0')}`).date_to
  } else if (filter.period === 'recent') {
    from = recentMonths(current, 6)[0] + '-01'; to = today
  } else {
    const month = validMonth(filter.period) ? filter.period : validMonth(filter.month) ? filter.month : current
    const period = monthPeriod(month); from = period.date_from; to = period.date_to
  }
  // Completed periods keep their full dates; the current period ends today.
  if (filter.period !== 'custom' && from <= today && to > today) to = today
  if (!validReportDay(from) || !validReportDay(to)) throw new Error('Vui lòng chọn ngày hợp lệ.')
  if (from > to) throw new Error('Từ ngày không được sau Đến ngày.')
  if ((Date.parse(to) - Date.parse(from)) / 86400000 >= 366) throw new Error('Mỗi lần xem báo cáo tối đa 366 ngày.')
  return { date_from: from, date_to: to }
}
export function reportQuery(filter, now = new Date()) {
  const query = reportPeriod(filter, now)
  for (const key of ['category_id', 'brand_id', 'product_id']) if (filter[key]) query[key] = filter[key]
  return query
}
export function reportSearch(filter, tab = 'revenue') {
  const params = new URLSearchParams()
  if (tab !== 'revenue') params.set('tab', tab)
  for (const key of Object.keys(defaultReportFilters())) if (filter[key] !== '' && filter[key] != null) params.set(key, filter[key])
  return params
}
export const reportRate = (count, total) => total > 0 ? (count / total * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + '%' : '0%'
export const reportRangeLabel = (from, to) => from === to ? formatDate(from) : `${formatDate(from)} – ${formatDate(to)}`
export const reportMargin = (value) => value == null ? '—' : Number(value).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + '%'
export function reportColumns(tab) {
  return tab === 'revenue'
    ? [['ProductName', 'Sản phẩm'], ['Quantity', 'SL bán'], ['Revenue', 'Doanh số'], ['Cost', 'Tổng giá nhập'], ['Profit', 'Lãi gộp'], ['Margin', 'Biên lãi']]
    : [['PeriodLabel', 'Tháng đặt hàng'], ['TotalOrders', 'Đơn đặt'], ['InProgressOrders', 'Đang xử lý'], ['DeliveredOrders', 'Đã giao'], ['CancelledOrders', 'Đã hủy'], ['CancelRate', 'Tỷ lệ hủy']]
}

