import { apiRequest } from './auth-api.js'

export function currentMonth(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit' }).formatToParts(now)
  return `${parts.find((part) => part.type === 'year').value}-${parts.find((part) => part.type === 'month').value}`
}

// Statistics use inclusive Vietnam calendar dates, rather than the browser's timezone.
export function monthPeriod(month) {
  const [year, number] = month.split('-').map(Number)
  const lastDay = new Date(Date.UTC(year, number, 0)).getUTCDate()
  return { date_from: `${month}-01`, date_to: `${month}-${lastDay}` }
}

export function getAdminData(accessToken, path, params = {}, signal) {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== '' && value != null))
  return apiRequest(`${path}${query.size ? `?${query}` : ''}`, { method: 'GET', accessToken, signal })
}

export function getOrderStatistics(accessToken, month, signal) {
  return getAdminData(accessToken, '/admin/statistics/orders', monthPeriod(month), signal)
}

export function getRevenueStatistics(accessToken, month, signal) {
  return getAdminData(accessToken, '/admin/statistics/revenue', monthPeriod(month), signal)
}

export function getRecentOrders(accessToken, signal) {
  // The API sorts by OrderedAt descending; latest orders are not restricted to this month.
  return getAdminData(accessToken, '/admin/orders', { page: 1, page_size: 4 }, signal)
}

export async function getLowStock(accessToken, signal) {
  // Total is the complete server-side count, including variants outside the first page.
  const result = await getAdminData(accessToken, '/admin/inventory/low-stock', { page: 1, page_size: 4 }, signal)
  const ids = [...new Set(result.Items.map((item) => item.ProductId))]
  const products = await Promise.allSettled(ids.map((id) => getAdminData(accessToken, `/admin/products/${id}`, {}, signal)))
  signal?.throwIfAborted()
  const names = new Map(ids.map((id, index) => [id, products[index].status === 'fulfilled' ? products[index].value.Name : null]))
  return { ...result, Items: result.Items.map((item) => ({ ...item, ProductName: names.get(item.ProductId) || item.VariantName || item.Sku })) }
}
