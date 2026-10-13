import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { currentMonth, getLowStock, getOrderStatistics, getRecentOrders, getRevenueStatistics, monthPeriod } from './admin-dashboard-api.js'
import { allowedMenu, sectionFromPath, sectionPath } from '../admin/routes.js'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })
const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

test('calendar months follow Vietnam time and inclusive month ends, including leap years', () => {
  assert.equal(currentMonth(new Date('2026-09-30T17:00:00Z')), '2026-10')
  assert.equal(currentMonth(new Date('2026-09-30T16:59:59Z')), '2026-09')
  assert.deepEqual(monthPeriod('2028-02'), { date_from: '2028-02-01', date_to: '2028-02-29' })
  assert.deepEqual(monthPeriod('2026-02'), { date_from: '2026-02-01', date_to: '2026-02-28' })
  assert.deepEqual(monthPeriod('2026-12'), { date_from: '2026-12-01', date_to: '2026-12-31' })
})

test('statistics and recent orders use existing backend paths, PascalCase responses and bearer authentication', async () => {
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return response(url.includes('/statistics/orders') ? { TotalOrders: 0, ByStatus: { Pending: 0 } } : url.includes('/revenue') ? { NetRevenue: '0.00' } : { Items: [], Total: 0 })
  }
  assert.equal((await getOrderStatistics('token', '2026-10')).TotalOrders, 0)
  assert.equal((await getRevenueStatistics('token', '2026-10')).NetRevenue, '0.00')
  assert.deepEqual((await getRecentOrders('token')).Items, [])
  assert.deepEqual(calls.map((call) => call.url), [
    '/api/admin/statistics/orders?date_from=2026-10-01&date_to=2026-10-31',
    '/api/admin/statistics/revenue?date_from=2026-10-01&date_to=2026-10-31',
    '/api/admin/orders?page=1&page_size=4',
  ])
  for (const { options } of calls) {
    assert.equal(options.method, 'GET')
    assert.equal(options.headers.Authorization, 'Bearer token')
    assert.equal(options.credentials, 'include')
  }
})

test('low-stock uses the full server count and resolves repeated products only once', async () => {
  const calls = []
  globalThis.fetch = async (url) => {
    calls.push(url)
    return response(url.includes('/low-stock') ? { Items: [
      { ProductVariantId: 'v1', ProductId: 'p1', VariantName: '128GB', Sku: 'A', StockQuantity: 0 },
      { ProductVariantId: 'v2', ProductId: 'p1', VariantName: '256GB', Sku: 'B', StockQuantity: 3 },
    ], Total: 23, Page: 1, PageSize: 4 } : { Name: 'Điện thoại' })
  }
  const data = await getLowStock('token')
  assert.equal(data.Total, 23)
  assert.equal(data.Items.length, 2)
  assert.equal(data.Items[0].ProductName, 'Điện thoại')
  assert.equal(data.Items[0].StockQuantity, 0)
  assert.equal(calls.filter((url) => url.includes('/products/')).length, 1)
})

test('missing product details keep stock alerts visible; an empty inventory makes no product requests', async () => {
  globalThis.fetch = async (url) => url.includes('/low-stock')
    ? response({ Items: [{ ProductVariantId: 'v1', ProductId: 'p1', VariantName: '256GB', Sku: 'A' }], Total: 1 })
    : response({ detail: 'Không tìm thấy sản phẩm' }, 404)
  assert.equal((await getLowStock('token')).Items[0].ProductName, '256GB')
  let calls = 0
  globalThis.fetch = async () => { calls += 1; return response({ Items: [], Total: 0 }) }
  assert.deepEqual((await getLowStock('token')).Items, [])
  assert.equal(calls, 1)
})

test('network errors and aborted reads are not converted into successful empty results', async () => {
  globalThis.fetch = async () => { throw new TypeError('offline') }
  await assert.rejects(getRecentOrders('token'), /Không kết nối được máy chủ/)
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(getRecentOrders('token', controller.signal), (error) => error.name === 'AbortError')
})

test('sidebar permissions filter groups and nested entries, while navigation paths round-trip', () => {
  const menu = allowedMenu(['products:view', 'brands:view', 'orders:view'])
  assert.deepEqual(menu.map((item) => item.id), ['overview', 'catalog', 'orders'])
  assert.deepEqual(menu.find((item) => item.id === 'catalog').children.map((item) => item.id), ['products', 'brands'])
  assert.deepEqual(allowedMenu([]).map((item) => item.id), ['overview'])
  for (const id of ['overview', 'orders', 'products', 'profile']) assert.equal(sectionFromPath(sectionPath(id)), id)
  assert.equal(sectionFromPath('/admin/orders/'), 'orders')
})
