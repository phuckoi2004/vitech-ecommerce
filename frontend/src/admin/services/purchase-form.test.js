// @vitest-environment node
import { beforeEach, expect, test, vi } from 'vitest'
import { savePurchaseDraft } from './purchase-form.js'

const api = vi.hoisted(() => ({ updatePurchase: vi.fn(), addPurchaseItem: vi.fn(), removePurchaseItem: vi.fn(), updatePurchaseItem: vi.fn() }))
vi.mock('./purchases.js', () => api)
const body = { SupplierId: 's1', Note: 'Đã sửa', Items: [{ ProductVariantId: 'v2', OrderedQuantity: 1, UnitPrice: '2000.00', Note: null }] }
beforeEach(() => vi.resetAllMocks())

test('header and the entire desired line set use one PATCH and return the server result', async () => {
  const saved = { PurchaseOrderId: 'po1', ...body, TotalAmount: '2000.00' }
  api.updatePurchase.mockResolvedValue(saved)
  expect(await savePurchaseDraft('token', 'po1', body)).toBe(saved)
  expect(api.updatePurchase).toHaveBeenCalledExactlyOnceWith('token', 'po1', body)
  for (const name of ['addPurchaseItem', 'removePurchaseItem', 'updatePurchaseItem']) expect(api[name]).not.toHaveBeenCalled()
})

test('failure is surfaced and retry sends the same complete set, without incremental add/delete calls', async () => {
  const failure = new Error('Phiếu không còn được phép sửa.')
  api.updatePurchase.mockRejectedValueOnce(failure).mockResolvedValueOnce(body)
  await expect(savePurchaseDraft('token', 'po1', body)).rejects.toBe(failure)
  await expect(savePurchaseDraft('token', 'po1', body)).resolves.toBe(body)
  expect(api.updatePurchase.mock.calls).toEqual([['token', 'po1', body], ['token', 'po1', body]])
  for (const name of ['addPurchaseItem', 'removePurchaseItem', 'updatePurchaseItem']) expect(api[name]).not.toHaveBeenCalled()
})
