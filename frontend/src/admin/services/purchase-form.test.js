// @vitest-environment node
import { beforeEach, expect, test, vi } from 'vitest'
import { savePurchaseDraft } from './purchase-form.js'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), addPurchaseItem: vi.fn(), removePurchaseItem: vi.fn(), updatePurchase: vi.fn(), updatePurchaseItem: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('./purchases.js', () => api)
let po
const body = { SupplierId: 's1', Note: 'Đã sửa', Items: [{ ProductVariantId: 'v2', OrderedQuantity: 1, UnitPrice: '2000.00', Note: null }] }
beforeEach(() => {
  vi.resetAllMocks()
  po = { PurchaseOrderId: 'po1', Status: 'Pending', SupplierId: 's1', Note: null, Items: [{ PurchaseOrderItemId: 'i1', ProductVariantId: 'v1', OrderedQuantity: 2, UnitPrice: '1000.00', ReceivedQuantity: 0, Note: null }] }
  api.getAdminData.mockImplementation(async () => structuredClone(po))
  api.addPurchaseItem.mockImplementation(async (_, __, line) => { po.Items.push({ ...line, PurchaseOrderItemId: 'i2', ReceivedQuantity: 0 }); return structuredClone(po) })
  api.removePurchaseItem.mockImplementation(async (_, __, id) => { po.Items = po.Items.filter((item) => item.PurchaseOrderItemId !== id); return structuredClone(po) })
  api.updatePurchase.mockImplementation(async (_, __, patch) => { po = { ...po, ...patch }; return structuredClone(po) })
})

test('a partially successful save reports its progress and retry resumes from fresh server data without adding the same SKU twice', async () => {
  api.removePurchaseItem.mockRejectedValueOnce(new Error('Lỗi kết nối.'))
  const checkpoint = vi.fn()
  await expect(savePurchaseDraft('token', 'po1', body, checkpoint)).rejects.toThrow('Đã lưu một phần thay đổi (1/3 bước)')
  expect(po.Items).toHaveLength(2)
  expect(checkpoint).toHaveBeenCalledTimes(1)
  expect(api.updatePurchase).not.toHaveBeenCalled()
  const result = await savePurchaseDraft('token', 'po1', body, checkpoint)
  expect(result.Items.map((item) => item.ProductVariantId)).toEqual(['v2'])
  expect(result.Note).toBe('Đã sửa')
  expect(api.addPurchaseItem).toHaveBeenCalledTimes(1)
  expect(api.removePurchaseItem).toHaveBeenCalledTimes(2)
  expect(api.getAdminData).toHaveBeenCalledTimes(2)
})

test('an approved order read at save time blocks every mutation, even when the form originally loaded Pending', async () => {
  po.Status = 'Approved'
  await expect(savePurchaseDraft('token', 'po1', body, vi.fn())).rejects.toThrow('không còn được phép sửa')
  for (const name of ['addPurchaseItem', 'removePurchaseItem', 'updatePurchase', 'updatePurchaseItem']) expect(api[name]).not.toHaveBeenCalled()
})

test('a committed add whose response was lost is discovered on retry and is never sent a second time', async () => {
  const original = api.addPurchaseItem.getMockImplementation()
  api.addPurchaseItem.mockImplementationOnce(async (...args) => { await original(...args); throw new Error('Mất phản hồi.'); })
  await expect(savePurchaseDraft('token', 'po1', body, vi.fn())).rejects.toThrow('Mất phản hồi.')
  const result = await savePurchaseDraft('token', 'po1', body, vi.fn())
  expect(result.Items.map((item) => item.ProductVariantId)).toEqual(['v2'])
  expect(api.addPurchaseItem).toHaveBeenCalledTimes(1)
})
