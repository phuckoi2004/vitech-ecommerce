// @vitest-environment node
import { afterEach, expect, test, vi } from 'vitest'
import { assignOrderSerials, confirmCodDelivery, releaseOrderSerial, updateOrderNote, updateOrderStatus } from './orders.js'

afterEach(() => vi.unstubAllGlobals())

test('order writes use the existing distinct workflow endpoints and encode path identifiers', async () => {
  const fetch = vi.fn(async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  await updateOrderStatus('access', 'order/id', { OrderStatus: 'Confirmed', Note: null })
  await confirmCodDelivery('access', 'order/id', { Note: 'Đã thu đủ tiền' })
  await updateOrderNote('access', 'order/id', { InternalNote: null })
  await assignOrderSerials('access', 'order/id', { Items: [{ OrderItemId: 'item', SerialNumbers: ['SN-01'] }] })
  await releaseOrderSerial('access', 'order/id', 'SN/01')
  expect(fetch.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
    ['/api/admin/orders/order%2Fid/status', 'POST'],
    ['/api/admin/orders/order%2Fid/confirm-cod-delivery', 'POST'],
    ['/api/admin/orders/order%2Fid', 'PATCH'],
    ['/api/admin/orders/order%2Fid/serials', 'POST'],
    ['/api/admin/orders/order%2Fid/serials/SN%2F01', 'DELETE'],
  ])
  expect(fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer access' && options.credentials === 'include')).toBe(true)
  expect(fetch.mock.calls.slice(0, 4).map(([, options]) => JSON.parse(options.body))).toEqual([
    { OrderStatus: 'Confirmed', Note: null }, { Note: 'Đã thu đủ tiền' }, { InternalNote: null }, { Items: [{ OrderItemId: 'item', SerialNumbers: ['SN-01'] }] },
  ])
  expect(fetch.mock.calls[4][1].body).toBeUndefined()
})

test('server workflow restrictions reach the UI without silently substituting another write', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ code: 'order_serials_incomplete', detail: 'Chưa gán đủ Serial/IMEI cho đơn hàng' }), { status: 409, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  await expect(updateOrderStatus('access', 'order', { OrderStatus: 'Shipping' })).rejects.toMatchObject({ code: 'order_serials_incomplete', message: 'Chưa gán đủ Serial/IMEI cho đơn hàng' })
  expect(fetch).toHaveBeenCalledTimes(1)
})
