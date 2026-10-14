import { request } from './client.js'
import { monthPeriod } from '../../lib/dashboard-periods.js'

export function getAdminData(accessToken, path, query = {}, signal) {
  return request(path, { accessToken, query, signal })
}

export async function getRevenueSeries(accessToken, months, signal) {
  const results = await Promise.allSettled(months.map((month) => getAdminData(accessToken, '/admin/statistics/revenue', monthPeriod(month), signal)))
  signal?.throwIfAborted()
  // Session failures must reach AuthProvider so it can refresh and retry.
  for (const result of results) if (result.status === 'rejected' && [401, 403].includes(result.reason.status)) throw result.reason
  return months.map((month, index) => results[index].status === 'fulfilled'
    ? { month, data: results[index].value, error: '' }
    : { month, data: null, error: results[index].reason.message })
}

export async function getDashboardStock(accessToken, signal) {
  const result = await getAdminData(accessToken, '/admin/inventory/low-stock', { page: 1, page_size: 4 }, signal)
  const ids = [...new Set(result.Items.map((item) => item.ProductId))]
  const products = await Promise.allSettled(ids.map((id) => getAdminData(accessToken, `/admin/products/${id}`, {}, signal)))
  signal?.throwIfAborted()
  for (const product of products) if (product.status === 'rejected' && product.reason.status === 401) throw product.reason
  const names = new Map(ids.map((id, index) => [id, products[index].status === 'fulfilled' ? products[index].value.Name : null]))
  return { ...result, Items: result.Items.map((item) => ({ ...item, ProductName: names.get(item.ProductId) || item.VariantName || item.Sku })) }
}

export function markNotificationRead(accessToken, notificationId) {
  return request(`/users/me/notifications/${notificationId}/read`, { method: 'POST', accessToken })
}

export function markAllNotificationsRead(accessToken) {
  return request('/users/me/notifications/read-all', { method: 'POST', accessToken })
}
