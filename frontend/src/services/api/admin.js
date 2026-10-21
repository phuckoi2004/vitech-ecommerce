import { request } from './client.js'
import { monthPeriod, vietnamToday } from '../../lib/dashboard-periods.js'

export function getAdminData(accessToken, path, query = {}, signal) {
  return request(path, { accessToken, query, signal })
}

export async function getRevenueSeries(accessToken, months, signal, today = vietnamToday()) {
  if (!months.length) return []
  const last = months.at(-1)
  const data = await getAdminData(accessToken, '/admin/statistics/reports/revenue', {
    date_from: months[0] + '-01', date_to: last === today.slice(0, 7) ? today : monthPeriod(last).date_to,
    page: 1, page_size: 1,
  }, signal)
  signal?.throwIfAborted()
  return months.map((month) => ({ month, error: '', data: months.length === 1 ? data.Summary :
    data.Chart.find((point) => point.DateFrom.slice(0, 7) === month) ?? null }))
}

export async function getDashboardStock(accessToken, signal) {
  const [empty, low] = await Promise.all(['out_of_stock', 'low_stock'].map((stock) =>
    getAdminData(accessToken, '/admin/variants', { status: 'Active', stock, page: 1, page_size: 4 }, signal)))
  signal?.throwIfAborted()
  return { OutOfStockTotal: empty.Total, LowStockTotal: low.Total,
    Items: [...empty.Items, ...low.Items].slice(0, 4).map((item) => ({ ...item, ProductName: item.Name })) }
}

export function markNotificationRead(accessToken, notificationId) {
  return request(`/users/me/notifications/${notificationId}/read`, { method: 'POST', accessToken })
}

export function markAllNotificationsRead(accessToken) {
  return request('/users/me/notifications/read-all', { method: 'POST', accessToken })
}
