import { beforeEach, expect, test, vi } from 'vitest'
const api = vi.hoisted(() => ({ getAdminData: vi.fn(), request: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../../services/api/client.js', () => ({ request: api.request }))
import { createPromotion, updatePromotion, updatePromotionTargets, deletePromotion, getPromotionDirectory } from './promotions.js'
beforeEach(() => vi.resetAllMocks())
test('search directory reads all pages and deduplicates without mixing coupon APIs', async () => {
  api.getAdminData.mockImplementation(async (_, path, query) => ({ Total: 201, Items: [{ PromotionId: 'p' + query.page, Name: path }, ...(query.page === 3 ? [{ PromotionId: 'p1', Name: 'updated' }] : [])] }))
  const data = await getPromotionDirectory('token', new AbortController().signal)
  expect(data).toHaveLength(3)
  expect(api.getAdminData).toHaveBeenCalledTimes(3)
  expect(api.getAdminData.mock.calls.every(([, path]) => path === '/admin/promotions')).toBe(true)
})
test('failed later page rejects instead of exposing misleading partial list/count', async () => {
  api.getAdminData.mockResolvedValueOnce({ Items: [{ PromotionId: 'p1' }], Total: 101 }).mockRejectedValueOnce(new Error('Không tải được trang 2'))
  await expect(getPromotionDirectory('token')).rejects.toThrow('Không tải được trang 2')
})
test('mutations use existing endpoints, encoded IDs and HTTP methods', async () => {
  await createPromotion('t', { Name: 'Test' }); await updatePromotion('t', 'p/1', { Name: 'Edited' }); await updatePromotionTargets('t', 'p/1', { ProductIds: ['parent'], CategoryIds: [] }); await deletePromotion('t', 'p/1')
  expect(api.request.mock.calls.map(([path, config]) => [path, config.method])).toEqual([['/admin/promotions', 'POST'], ['/admin/promotions/p%2F1', 'PATCH'], ['/admin/promotions/p%2F1/targets', 'PUT'], ['/admin/promotions/p%2F1', 'DELETE']])
})
