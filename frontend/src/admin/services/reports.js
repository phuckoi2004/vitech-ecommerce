import { getAdminData } from '../../services/api/admin.js'
import { monthLabel } from '../../lib/dashboard-periods.js'
import { reportRate } from '../lib/reports.js'

export const getReportOptions = (token, signal) => getAdminData(token, '/admin/statistics/report-options', {}, signal)
export function formatReport(data, tab) {
  if (!data) return null
  const firstMonth = data.Period.DateFrom.slice(0, 7), lastMonth = data.Period.DateTo.slice(0, 7)
  const singleMonth = firstMonth === lastMonth
  // A single-month response may contain weekly chart points. Use the period's
  // exact totals for its one bar; five-month ranges already return monthly points.
  const chart = singleMonth ? [{ ...data.Summary, DateFrom: data.Period.DateFrom,
    DateTo: data.Period.DateTo, Label: monthLabel(firstMonth) }] : data.Chart.map((point) => ({
      ...point, Label: monthLabel(point.DateFrom.slice(0, 7)),
    }))
  return { ...data, Chart: chart,
    Summary: { ...data.Summary, PeakRevenue: singleMonth ? data.Summary.Revenue : data.Summary.PeakRevenue },
    Items: data.Items.map((row) => ({ ...row,
    PeriodLabel: monthLabel(row.DateFrom.slice(0, 7)),
    ...(tab === 'orders' ? { CancelRate: reportRate(row.CancelledOrders, row.TotalOrders) } : {}),
  })) }
}
