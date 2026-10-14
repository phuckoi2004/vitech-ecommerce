// @vitest-environment node
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { getReviewDirectory, hideReview } from './reviews.js'
const api = vi.hoisted(() => ({ getAdminData: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
beforeEach(() => vi.resetAllMocks())
afterEach(() => vi.unstubAllGlobals())

test('the directory includes every product page, historical products and every review page before sorting', async () => {
  const products = Array.from({ length: 101 }, (_, index) => ({ ProductId: 'p' + index, Name: 'Sản phẩm ' + index, ReviewCount: 0 }))
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/admin/products') return { Items: products.slice((query.page - 1) * 100, query.page * 100), Total: 101 }
    if (path === '/admin/products/p100/reviews') {
      const rows = Array.from({ length: 101 }, (_, index) => ({ ReviewId: 'r' + index, ProductId: 'p100', CreatedAt: '2026-10-14T06:00:00Z', IsDeleted: true }))
      return { Items: rows.slice((query.page - 1) * 100, query.page * 100), Total: 101 }
    }
    return { Items: [], Total: 0 }
  })
  const signal = new AbortController().signal
  const result = await getReviewDirectory('token', signal)
  expect(result).toHaveLength(101)
  expect(result.every((review) => review.ProductName === 'Sản phẩm 100' && review.IsDeleted)).toBe(true)
  expect(api.getAdminData).toHaveBeenCalledWith('token', '/admin/products', { include_deleted: true, page: 2, page_size: 100 }, signal)
  expect(api.getAdminData).toHaveBeenCalledWith('token', '/admin/products/p100/reviews', { include_deleted: true, page: 2, page_size: 100 }, signal)
})
test('failed product reviews reject the entire directory rather than reporting an incomplete zero count', async () => {
  api.getAdminData.mockResolvedValueOnce({ Items: [{ ProductId: 'p1', Name: 'Sản phẩm' }], Total: 1 }).mockRejectedValueOnce(new Error('Lỗi tải đánh giá.'))
  await expect(getReviewDirectory('token')).rejects.toThrow('Lỗi tải đánh giá.')
})
test('401 errors take priority over other simultaneous errors so the auth layer can refresh the session', async () => {
  const session = Object.assign(new Error('Phiên hết hạn.'), { status: 401 })
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/admin/products') return { Items: [{ ProductId: 'p1' }, { ProductId: 'p2' }], Total: 2 }
    if (path.includes('/p1/')) throw new Error('Lỗi mạng.')
    throw session
  })
  await expect(getReviewDirectory('token')).rejects.toBe(session)
})
test('an aborted load does not proceed to the review endpoints', async () => {
  const controller = new AbortController()
  api.getAdminData.mockImplementation(async () => { controller.abort(); return { Items: [{ ProductId: 'p1' }], Total: 1 } })
  await expect(getReviewDirectory('token', controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
  expect(api.getAdminData).toHaveBeenCalledTimes(1)
})
test('moderation posts only an optional reason to the existing hide endpoint and never deletes records or changes ratings directly', async () => {
  const fetch = vi.fn(async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  await hideReview('token', 'r/id', ' Nội dung không phù hợp ')
  await hideReview('token', 'r2', '  ')
  expect(fetch.mock.calls[0][0]).toBe('/api/admin/reviews/r%2Fid/hide')
  expect(fetch.mock.calls[0][1].method).toBe('POST')
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer token')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ DeleteReason: 'Nội dung không phù hợp' })
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ DeleteReason: null })
})
