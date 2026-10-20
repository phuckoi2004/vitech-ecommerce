// @vitest-environment node
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { addPurchaseItem, deletePurchase, closePurchase, createPurchase, decidePurchase, getPurchaseDirectory, receivePurchase, removePurchaseItem, updatePurchase, updatePurchaseItem } from './purchases.js'
const api = vi.hoisted(() => ({ getAdminData: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
beforeEach(() => vi.resetAllMocks())
afterEach(() => vi.unstubAllGlobals())

test('directory loads every summary page and actual detail quantities before filtering/export', async () => {
  const rows = Array.from({ length: 101 }, (_, index) => ({ PurchaseOrderId: 'po-' + index }))
  api.getAdminData.mockImplementation(async (_, path, query) => path === '/admin/purchase-orders' ? { Items: rows.slice((query.page - 1) * 100, query.page * 100), Total: 101 } : { PurchaseOrderId: path.split('/').at(-1), Items: [{ OrderedQuantity: 3 }] })
  const signal = new AbortController().signal
  const result = await getPurchaseDirectory('access', signal)
  expect(result).toHaveLength(101)
  expect(result.at(-1)).toEqual({ PurchaseOrderId: 'po-100', Items: [{ OrderedQuantity: 3 }] })
  expect(api.getAdminData.mock.calls.every(([token, , , passed]) => token === 'access' && passed === signal)).toBe(true)
})

test('a failed detail rejects the complete directory instead of substituting zero quantity', async () => {
  api.getAdminData.mockResolvedValueOnce({ Items: [{ PurchaseOrderId: 'po' }], Total: 1 }).mockRejectedValueOnce(new Error('Lỗi chi tiết'))
  await expect(getPurchaseDirectory('access')).rejects.toThrow('Lỗi chi tiết')
})

test('all writes target the existing use-case endpoints and encode both order and item IDs', async () => {
  const fetch = vi.fn(async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const line = { ProductVariantId: 'v1', OrderedQuantity: 2, UnitPrice: '1500000.00', Note: null }
  await createPurchase('access', { SupplierId: 's1', Note: null, Items: [line] })
  await updatePurchase('access', 'po/id', { Note: null })
  await addPurchaseItem('access', 'po/id', line)
  await updatePurchaseItem('access', 'po/id', 'item/id', { OrderedQuantity: 3 })
  await removePurchaseItem('access', 'po/id', 'item/id')
  await decidePurchase('access', 'po/id', { Status: 'Rejected', RejectReason: 'Sai sản phẩm' })
  await receivePurchase('access', 'po/id', { Items: [{ PurchaseOrderItemId: 'item/id', Quantity: 1, SerialNumbers: ['SN1'] }], Note: null })
  await closePurchase('access', 'po/id', { Reason: 'NCC giao thiếu' })
  await deletePurchase('access', 'po/id')
  expect(fetch.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
    ['/api/admin/purchase-orders', 'POST'], ['/api/admin/purchase-orders/po%2Fid', 'PATCH'],
    ['/api/admin/purchase-orders/po%2Fid/items', 'POST'], ['/api/admin/purchase-orders/po%2Fid/items/item%2Fid', 'PATCH'], ['/api/admin/purchase-orders/po%2Fid/items/item%2Fid', 'DELETE'],
    ['/api/admin/purchase-orders/po%2Fid/decision', 'POST'], ['/api/admin/purchase-orders/po%2Fid/receive', 'POST'], ['/api/admin/purchase-orders/po%2Fid/close', 'POST'], ['/api/admin/purchase-orders/po%2Fid', 'DELETE'],
  ])
  expect(fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer access' && options.credentials === 'include')).toBe(true)
  expect(JSON.parse(fetch.mock.calls[6][1].body)).toEqual({ Items: [{ PurchaseOrderItemId: 'item/id', Quantity: 1, SerialNumbers: ['SN1'] }], Note: null })
  expect(fetch.mock.calls[8][1].body).toBeUndefined()
})
