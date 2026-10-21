// @vitest-environment node
import { afterEach, describe, expect, test, vi } from 'vitest'
import { getDashboardStock, getRevenueSeries, markAllNotificationsRead, markNotificationRead } from './admin.js'

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => vi.unstubAllGlobals())

describe('dashboard API contracts', () => {
  test('six-month series uses the same sales report source as the summary in one request', async () => {
    const fetch = vi.fn(async () => json({ Summary: {}, Chart: [
      { DateFrom: '2026-09-01', Revenue: '434000', Cost: '300000', Profit: '134000' },
      { DateFrom: '2026-10-01', Revenue: '200000', Cost: null, Profit: null },
    ] }))
    vi.stubGlobal('fetch', fetch)
    const result = await getRevenueSeries('access', ['2026-09','2026-10'], undefined, '2026-10-21')
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][0]).toBe('/api/admin/statistics/reports/revenue?date_from=2026-09-01&date_to=2026-10-21&page=1&page_size=1')
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer access')
    expect(result[0].data.Revenue).toBe('434000')
    expect(result[1].data.Profit).toBeNull()
  })

  test('auth and API errors propagate instead of silently replacing monthly sales with zero', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'Phiên hết hạn' }, 401)))
    await expect(getRevenueSeries('expired',['2026-10'])).rejects.toMatchObject({ status: 401 })
    vi.stubGlobal('fetch', vi.fn(async () => json({},503)))
    await expect(getRevenueSeries('access',['2026-09','2026-10'])).rejects.toMatchObject({ status: 503 })
  })

  test('inventory reads existing product-list SKUs and separates empty from low stock', async () => {
    const fetch = vi.fn(async (url) => {
      const empty = new URL(url, 'http://local').searchParams.get('stock') === 'out_of_stock'
      return json({ Items: [{ ProductVariantId: empty ? 'v1' : 'v2', ProductId: 'p1', Name: 'Điện thoại', VariantName: empty ? '128GB' : '256GB', StockQuantity: empty ? 0 : 2 }], Total: empty ? 10 : 12 })
    })
    vi.stubGlobal('fetch', fetch)
    const result = await getDashboardStock('access')
    expect(result).toMatchObject({ OutOfStockTotal: 10, LowStockTotal: 12 })
    expect(result.Items[0]).toMatchObject({ ProductName: 'Điện thoại', StockQuantity: 0 })
    expect(fetch).toHaveBeenCalledTimes(2)
    for (const [url] of fetch.mock.calls) {
      expect(url).toContain('/api/admin/variants?status=Active&stock=')
      expect(url).not.toContain('/products/')
    }
  })

  test('notification read actions use the authenticated backend endpoints', async () => {
    const fetch = vi.fn(async () => json({ Count: 1 }))
    vi.stubGlobal('fetch', fetch)
    await markNotificationRead('access', 'n1')
    await markAllNotificationsRead('access')
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/users/me/notifications/n1/read', '/api/users/me/notifications/read-all'])
    expect(fetch.mock.calls.every(([, options]) => options.method === 'POST' && options.headers.Authorization === 'Bearer access')).toBe(true)
  })
})
