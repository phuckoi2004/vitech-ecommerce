// @vitest-environment node
import { afterEach, describe, expect, test, vi } from 'vitest'
import { getDashboardStock, getRevenueSeries, markAllNotificationsRead, markNotificationRead } from './admin.js'

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => vi.unstubAllGlobals())

describe('dashboard API contracts', () => {
  test('revenue requests use inclusive month dates and bearer access for all five months', async () => {
    const fetch = vi.fn(async () => json({ OrderCount: 0, NetRevenue: '0.00' }))
    vi.stubGlobal('fetch', fetch)
    const months = ['2026-10', '2026-11', '2026-12', '2027-01', '2027-02']
    const result = await getRevenueSeries('access', months)
    expect(result.map((item) => item.month)).toEqual(months)
    expect(fetch).toHaveBeenCalledTimes(5)
    expect(fetch.mock.calls[4][0]).toBe('/api/admin/statistics/revenue?date_from=2027-02-01&date_to=2027-02-28')
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer access')
    expect(fetch.mock.calls[0][1].credentials).toBe('include')
  })

  test('session failures reach AuthProvider while non-auth monthly failures stay distinguishable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'Phiên hết hạn' }, 401)))
    await expect(getRevenueSeries('expired', ['2026-10'])).rejects.toMatchObject({ status: 401 })
    vi.stubGlobal('fetch', vi.fn(async (url) => url.includes('2026-09') ? json({}, 503) : json({ OrderCount: 1, NetRevenue: '10.00' })))
    const result = await getRevenueSeries('access', ['2026-09', '2026-10'])
    expect(result[0].data).toBeNull()
    expect(result[0].error).toBeTruthy()
    expect(result[1].data.NetRevenue).toBe('10.00')
  })

  test('inventory preserves the complete count and looks up duplicate products only once', async () => {
    const fetch = vi.fn(async (url) => url.includes('/low-stock') ? json({ Items: [
      { ProductVariantId: 'v1', ProductId: 'p1', VariantName: '128GB', StockQuantity: 0 },
      { ProductVariantId: 'v2', ProductId: 'p1', VariantName: '256GB', StockQuantity: 2 },
    ], Total: 22 }) : json({ Name: 'Điện thoại' }))
    vi.stubGlobal('fetch', fetch)
    const result = await getDashboardStock('access')
    expect(result.Total).toBe(22)
    expect(result.Items[0]).toMatchObject({ ProductName: 'Điện thoại', StockQuantity: 0 })
    expect(fetch.mock.calls.filter(([url]) => url.includes('/products/'))).toHaveLength(1)
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
