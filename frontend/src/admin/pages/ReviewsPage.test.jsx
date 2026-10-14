import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), hideReview: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/reviews.js', async (original) => ({ ...await original(), hideReview: api.hideReview }))
const permissions = ['admin.portal', 'reviews:view', 'reviews:delete', 'products:view']
const product = { ProductId: 'p1', Name: 'Sản phẩm từ API', ReviewCount: 0, IsDeleted: false }
const base = { ReviewId: 'r1', ProductId: 'p1', UserId: 'customer1', OrderItemId: 'item1', User: { FullName: 'Khách hàng từ API' }, Rating: 4, Content: 'Bình luận thật\nDòng thứ hai', CreatedAt: '2026-10-13T17:30:00Z', UpdatedAt: '2026-10-13T17:30:00Z', Images: [], IsDeleted: false, DeleteReason: null, DeletedAt: null }
let reviews, products
function renderPage(path = '/admin/reviews', granted = permissions, role = 'Admin') {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
function paged(rows, query) { return { Items: structuredClone(rows.slice((query.page - 1) * query.page_size, query.page * query.page_size)), Total: rows.length } }
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-14T06:00:00Z'))
  vi.resetAllMocks(); reviews = []; products = [structuredClone(product)]
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/products') return paged(products, query)
    if (/^\/admin\/products\/[^/]+\/reviews$/.test(path)) return paged(reviews.filter((review) => path.includes('/' + review.ProductId + '/')), query)
    const review = reviews.find((review) => path === '/admin/reviews/' + review.ReviewId)
    if (review) return structuredClone(review)
    throw new Error('Không tìm thấy đánh giá.')
  })
  api.hideReview.mockImplementation(async (_, id, reason) => { reviews = reviews.map((review) => review.ReviewId === id ? { ...review, IsDeleted: true, DeleteReason: reason.trim() || null, DeletedAt: '2026-10-14T06:00:00Z' } : review); return structuredClone(reviews.find((review) => review.ReviewId === id)) })
})
afterEach(() => vi.useRealTimers())

test('the empty page preserves six Figma headers and zero counts, with the correct title, breadcrumb and sidebar selection', async () => {
  renderPage()
  await screen.findByText('Chưa có đánh giá.')
  expect(screen.getByRole('heading', { level: 1, name: 'Quản lý đánh giá' })).toBeInTheDocument()
  expect(within(screen.getByRole('banner')).getByText('/ Đánh giá')).toBeInTheDocument()
  expect(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Đánh giá', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Khách hàng', 'Sản phẩm', 'Số sao', 'Bình luận', 'Thời gian đánh giá', 'Thao tác'])
  expect(screen.getByText('0 đánh giá')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 đánh giá')).toBeInTheDocument()
  expect(screen.queryByText('Nguyễn Minh Anh')).not.toBeInTheDocument()
})
test('the list displays actual customer/product names, correct stars and Vietnam timestamps without account lookups', async () => {
  reviews = [structuredClone(base)]
  renderPage()
  await screen.findByText('Khách hàng từ API')
  expect(screen.getByText('Sản phẩm từ API')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: '4 trên 5 sao' })).toHaveTextContent('★★★★☆')
  expect(screen.getByText('14/10/2026 00:30')).toBeInTheDocument()
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/users'))).toBe(false)
  const row = screen.getAllByRole('row')[1]
  expect(row.querySelector('[data-supplier-icon="view"]')).toHaveAttribute('width', '18')
  expect(row.querySelector('[data-supplier-icon="delete"]')).toHaveAttribute('width', '24')
})
test('time and star filters apply together, preserve URL history, reset pagination and clear correctly', async () => {
  reviews = Array.from({ length: 7 }, (_, index) => ({ ...structuredClone(base), ReviewId: 'r' + index, Rating: index ? 3 : 4 }))
  const router = renderPage('/admin/reviews?page=2')
  await screen.findByText('7 đánh giá')
  fireEvent.change(screen.getByRole('combobox', { name: 'Thời gian' }), { target: { value: '7days' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Số sao' }), { target: { value: '4' } })
  expect(screen.getByText('7 đánh giá')).toBeInTheDocument()
  fireEvent.submit(screen.getByRole('search'))
  await screen.findByText('1 đánh giá')
  expect(router.state.location.search).toContain('rating=4')
  expect(router.state.location.search).not.toContain('page=')
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  await screen.findByText('7 đánh giá')
  await act(() => router.navigate(-1))
  await screen.findByText('1 đánh giá')
  expect(screen.getByRole('combobox', { name: 'Số sao' })).toHaveValue('4')
})
test('the detail icon reads fresh data and shows the full comment and real review images', async () => {
  reviews = [{ ...structuredClone(base), Images: [{ ReviewImageId: 'image1', ImageUrl: 'https://storage.example.com/review.jpg', DisplayOrder: 0 }] }]
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Chi tiết đánh giá của Khách hàng từ API' }))
  const dialog = screen.getByRole('dialog', { name: 'Chi tiết đánh giá' })
  await within(dialog).findByText('14/10/2026 00:30')
  expect(within(dialog).queryByText('Đã mua hàng xác thực')).not.toBeInTheDocument()
  expect(dialog).toHaveClass('w-[560px]')
  expect(within(dialog).getByRole('region', { name: 'Bình luận đầy đủ' }).querySelector('p').textContent).toBe(base.Content)
  expect(within(dialog).getByRole('img', { name: 'Ảnh đánh giá 1' })).toHaveAttribute('src', 'https://storage.example.com/review.jpg')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/reviews/r1', {}, expect.any(AbortSignal))
})
test('trash opens confirmation and sends the typed reason only after confirmation; hidden records stay in audit history', async () => {
  reviews = [structuredClone(base)]
  const router = renderPage('/admin/reviews?rating=4')
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa đánh giá của Khách hàng từ API' }))
  const dialog = screen.getByRole('dialog', { name: 'Xóa đánh giá?' })
  const reason = await within(dialog).findByRole('textbox', { name: 'Lý do xóa' })
  expect(within(dialog).getByRole('button', { name: 'Xác nhận xóa' })).toBeDisabled()
  expect(api.hideReview).not.toHaveBeenCalled()
  fireEvent.change(reason, { target: { value: ' Nội dung không phù hợp ' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  await waitFor(() => expect(api.hideReview).toHaveBeenCalledWith('access-for-test', 'r1', 'Nội dung không phù hợp'))
  await screen.findByText('Đã ẩn')
  expect(screen.getByRole('button', { name: 'Xóa đánh giá của Khách hàng từ API' })).toBeDisabled()
  expect(router.state.location.search).toBe('?rating=4')
  expect(reviews).toHaveLength(1)
})
test('view-only permissions block deletion controls and direct delete URLs before detail reads', async () => {
  reviews = [structuredClone(base)]
  renderPage('/admin/reviews?dialog=delete&review=r1', permissions.filter((permission) => permission !== 'reviews:delete'))
  await screen.findByText('1 đánh giá')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Xóa đánh giá/ })).not.toBeInTheDocument()
  expect(api.getAdminData.mock.calls.some(([, path]) => path === '/admin/reviews/r1')).toBe(false)
})
test('a stale visible list cannot re-hide a review already moderated on the server', async () => {
  reviews = [structuredClone(base)]
  renderPage()
  await screen.findByText('1 đánh giá')
  reviews[0].IsDeleted = true
  fireEvent.click(screen.getByRole('button', { name: 'Xóa đánh giá của Khách hàng từ API' }))
  const dialog = screen.getByRole('dialog')
  await within(dialog).findByText('Đánh giá này đã được ẩn, không cần xóa lại.')
  expect(within(dialog).getByRole('button', { name: 'Xác nhận xóa' })).toBeDisabled()
  expect(api.hideReview).not.toHaveBeenCalled()
})
test('failed moderation retains the reason and blocks duplicate writes, dismissal and Escape while retrying', async () => {
  reviews = [structuredClone(base)]
  api.hideReview.mockRejectedValueOnce(new Error('Lỗi kết nối.'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa đánh giá của Khách hàng từ API' }))
  const dialog = screen.getByRole('dialog')
  const reason = await within(dialog).findByRole('textbox', { name: 'Lý do xóa' })
  fireEvent.change(reason, { target: { value: 'Giữ lý do' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  const failure = await screen.findByRole('dialog', { name: 'Không thể xóa đánh giá' })
  expect(within(failure).getByRole('alert')).toHaveTextContent('Lỗi kết nối.')
  expect(failure).toHaveClass('w-[480px]')
  fireEvent.click(within(failure).getByRole('button', { name: 'Đóng' }))
  const restored = await within(dialog).findByRole('textbox', { name: 'Lý do xóa' })
  expect(restored).toHaveValue('Giữ lý do')
  let finish
  api.hideReview.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  expect(within(dialog).getByRole('button', { name: 'Hủy', exact: true })).toBeDisabled()
  fireEvent.submit(restored.closest('form'))
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  expect(api.hideReview).toHaveBeenCalledTimes(2)
  expect(dialog).toBeInTheDocument()
  await act(async () => finish({ ...base, IsDeleted: true }))
})

test('the delete form requires a real reason and previews the selected review without changing the page URL', async () => {
  reviews = [structuredClone(base)]
  const router = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa đánh giá của Khách hàng từ API' }))
  const dialog = screen.getByRole('dialog', { name: 'Xóa đánh giá?' })
  const input = await within(dialog).findByRole('textbox', { name: 'Lý do xóa' })
  expect(dialog).toHaveClass('w-[500px]', 'min-h-[390px]')
  expect(dialog.className).toContain('backdrop:backdrop-blur-[2px]')
  const preview = within(dialog).getByRole('region', { name: 'Đánh giá sẽ được xóa' })
  expect(preview).toHaveTextContent('Sản phẩm từ API')
  expect(preview.querySelector('p:last-child').textContent).toBe('“' + base.Content + '”')
  fireEvent.change(input, { target: { value: '   ' } })
  expect(within(dialog).getByRole('button', { name: 'Xác nhận xóa' })).toBeDisabled()
  fireEvent.submit(input.closest('form'))
  expect(api.hideReview).not.toHaveBeenCalled()
  expect(router.state.location.pathname).toBe('/admin/reviews')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Hủy', exact: true }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('a lost response is rechecked after closing the error; an already hidden review cannot be submitted again', async () => {
  reviews = [structuredClone(base)]
  api.hideReview.mockImplementationOnce(async () => { reviews[0].IsDeleted = true; reviews[0].DeleteReason = 'Đã kiểm duyệt'; throw new Error('Mất phản hồi.'); })
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa đánh giá của Khách hàng từ API' }))
  const dialog = screen.getByRole('dialog')
  const input = await within(dialog).findByRole('textbox', { name: 'Lý do xóa' })
  fireEvent.change(input, { target: { value: 'Đã kiểm duyệt' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận xóa' }))
  const error = await screen.findByRole('dialog', { name: 'Không thể xóa đánh giá' })
  expect(within(error).queryByText(/giữ nguyên trong cơ sở dữ liệu/)).not.toBeInTheDocument()
  expect(screen.queryByText('Đã ẩn đánh giá khỏi trang sản phẩm và cập nhật điểm đánh giá của sản phẩm.')).not.toBeInTheDocument()
  fireEvent.click(within(error).getByRole('button', { name: 'Đóng' }))
  await within(dialog).findByText('Đánh giá này đã được ẩn, không cần xóa lại.')
  expect(within(dialog).getByRole('button', { name: 'Xác nhận xóa' })).toBeDisabled()
  expect(api.hideReview).toHaveBeenCalledTimes(1)
})
test.each([['Staff', permissions], ['Admin', ['admin.portal']]])('%s without admin review access never calls the domain endpoints', async (role, granted) => {
  renderPage('/admin/reviews', granted, role)
  await screen.findByText('Không có quyền truy cập')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/'))).toBe(false)
})
test('read errors remain distinct from zero reviews and can be retried', async () => {
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/products/p1/reviews' && failed ? Promise.reject(new Error('Không tải được đánh giá.')) : original(...args))
  renderPage()
  await screen.findByText('Không tải được đánh giá.')
  expect(screen.queryByText('0 đánh giá')).not.toBeInTheDocument()
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Chưa có đánh giá.')
})
test('out-of-range pages clamp after all reviews load and unchanged row actions remain available', async () => {
  reviews = Array.from({ length: 7 }, (_, index) => ({ ...structuredClone(base), ReviewId: 'r' + index }))
  const router = renderPage('/admin/reviews?page=99')
  await waitFor(() => expect(router.state.location.search).toBe('?page=2'))
  await screen.findByText('Hiển thị 6–7 trong 7 đánh giá')
  expect(screen.getAllByRole('button', { name: 'Chi tiết đánh giá của Khách hàng từ API' })).toHaveLength(2)
})
