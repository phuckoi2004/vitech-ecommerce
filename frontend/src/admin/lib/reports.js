import { browserMonth, monthLabel, monthPeriod, recentMonths } from '../../lib/dashboard-periods.js'
import { formatDate } from '../../lib/format.js'

export const REPORT_TABS = { revenue: 'Thống kê theo doanh thu', orders: 'Thống kê theo số lượng đơn hàng' }
export const REPORT_PAGE_SIZE = 10
export function reportPeriods(now = new Date()) {
  const year = now.getFullYear()
  return [
    ...Array.from({ length: 12 }, (_, index) => {
      const month = `${year}-${String(index + 1).padStart(2, '0')}`
      return [month, monthLabel(month)]
    }),
    ['recent', '5 tháng gần nhất'],
  ]
}

export function defaultReportFilters(now = new Date()) {
  return { period: browserMonth(now), category_id: '', brand_id: '', product_id: '' }
}

export function reportPeriod(filter, now = new Date()) {
  const month = browserMonth(now)
  if (filter.period === 'recent') {
    const months = recentMonths(month)
    return { date_from: monthPeriod(months[0]).date_from, date_to: monthPeriod(month).date_to }
  }
  return monthPeriod(/^\d{4}-(0[1-9]|1[0-2])$/.test(filter.period ?? '') ? filter.period : month)
}

export function reportQuery(filter, now = new Date()) {
  const query = reportPeriod(filter, now)
  for (const key of ['category_id', 'brand_id', 'product_id']) {
    if (filter[key]) query[key] = filter[key]
  }
  return query
}

export const reportRate = (count, total) => total > 0 ? (count / total * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + '%' : '0%'
export const reportRangeLabel = (from, to) => from === to ? formatDate(from) : `${formatDate(from)} – ${formatDate(to)}`

export function reportColumns(tab) {
  return tab === 'revenue'
    ? [['PeriodLabel', 'Thời gian'], ['ProductName', 'Sản phẩm'], ['CategoryName', 'Danh mục'], ['BrandName', 'Thương hiệu'], ['Revenue', 'Doanh thu']]
    : [['PeriodLabel', 'Thời gian'], ['TotalOrders', 'Tổng đơn'], ['DeliveredOrders', 'Giao thành công'], ['CancelledOrders', 'Đã hủy'], ['CancelRate', 'Tỷ lệ hủy']]
}

