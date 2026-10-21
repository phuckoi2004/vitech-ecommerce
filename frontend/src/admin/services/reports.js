import { getAdminData } from '../../services/api/admin.js'
import { monthLabel } from '../../lib/dashboard-periods.js'
import { reportRate } from '../lib/reports.js'

export const getReportOptions = (token, signal) => getAdminData(token, '/admin/statistics/report-options', {}, signal)
export function formatReport(data, tab) {
  if (!data) return null
  return { ...data, Items: (data.Items ?? []).map((row) => ({ ...row,
    ...(tab === 'orders' ? { PeriodLabel: monthLabel(row.DateFrom.slice(0, 7)), CancelRate: reportRate(row.CancelledOrders, row.TotalOrders) } : {}),
  })) }
}
