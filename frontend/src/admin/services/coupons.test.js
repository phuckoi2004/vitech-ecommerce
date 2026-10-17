import { beforeEach, expect, test, vi } from 'vitest'
const api = vi.hoisted(() => ({ getAdminData: vi.fn(), request: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../../services/api/client.js', () => ({ request: api.request }))
import { getCouponDirectory, createCoupon, updateCoupon, deleteCoupon } from './coupons.js'
beforeEach(() => vi.resetAllMocks())

test('all promotion pages are joined with their coupon lists; newest codes come first', async () => {
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/admin/promotions') return { Total: 101, Items: [{ PromotionId: query.page === 1 ? 'p/1' : 'p2', Name: 'Chương trình ' + query.page }] }
    return [{ CouponId: path.includes('p%2F1') ? 'c1' : 'c2', Code: path, CreatedAt: path.includes('p%2F1') ? '2026-10-01T00:00:00Z' : '2026-10-02T00:00:00Z' }]
  })
  const directory = await getCouponDirectory('t', new AbortController().signal)
  expect(directory.promotions).toHaveLength(2)
  expect(directory.items.map((row) => row.CouponId)).toEqual(['c2', 'c1'])
  expect(directory.items[1].Promotion.Name).toBe('Chương trình 1')
  expect(api.getAdminData.mock.calls.map(([, path]) => path)).toContain('/admin/promotions/p%2F1/coupons')
})
test('a failed coupon group rejects the whole directory instead of showing incomplete counts', async () => {
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/admin/promotions') return { Total: 2, Items: [{ PromotionId: 'p1' }, { PromotionId: 'p2' }] }
    if (path.includes('/p2/')) throw new Error('Lỗi danh sách mã')
    return [{ CouponId: 'c1', Code: 'ONE', CreatedAt: '2026-10-01T00:00:00Z' }]
  })
  await expect(getCouponDirectory('t')).rejects.toThrow('Lỗi danh sách mã')
})
test('an empty program directory is empty without requesting a nonexistent global coupon endpoint', async () => {
  api.getAdminData.mockResolvedValue({ Total: 0, Items: [] })
  expect(await getCouponDirectory('t')).toEqual({ promotions: [], items: [] })
  expect(api.getAdminData).toHaveBeenCalledTimes(1)
})
test('coupon mutations call existing endpoints and preserve null for unlimited usage', async () => {
  await createCoupon('t', { UsageLimit: null }); await updateCoupon('t', 'c/1', { IsActive: false }); await deleteCoupon('t', 'c/1')
  expect(api.request.mock.calls.map(([path, config]) => [path, config.method, config.body])).toEqual([['/admin/coupons', 'POST', { UsageLimit: null }], ['/admin/coupons/c%2F1', 'PATCH', { IsActive: false }], ['/admin/coupons/c%2F1', 'DELETE', undefined]])
})
