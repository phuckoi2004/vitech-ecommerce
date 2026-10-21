import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../../auth/context.js'
import { canEditReview, REVIEW_EDIT_WINDOW_MS } from '../../../lib/review-api.js'
import { makeAuth } from '../../../test/auth.js'
import ProductReviews from './ProductReviews.jsx'

const NOW = Date.parse('2026-10-15T05:00:00Z')
const product = { ProductId: 'p1', Name: 'Điện thoại kiểm thử', Slug: 'dien-thoai', ReviewCount: 0, AverageRating: '0.00',
  Variants: [{ ProductVariantId: 'v1', IsActive: true }, { ProductVariantId: 'old-variant', IsActive: false }] }
const review = (id, rating = 5, userId = 'other-user', overrides = {}) => ({
  ReviewId: id, ProductId: 'p1', Rating: rating, Content: `Nội dung đánh giá ${id}`, CreatedAt: '2026-10-14T05:00:00Z',
  UpdatedAt: '2026-10-14T05:00:00Z', User: { UserId: userId, FullName: userId === 'Customer-id' ? 'Khách hiện tại' : `Khách ${id}`, AvatarUrl: null },
  Images: [], ...overrides,
})
const order = (id = 'o1', overrides = {}) => ({
  OrderId: id, OrderCode: `VT-${id}`, OrderStatus: 'Delivered', OrderedAt: '2026-10-10T05:00:00Z',
  Items: [{ OrderItemId: `item-${id}`, ProductVariantId: 'v1', ProductName: product.Name, VariantInfo: 'Đen · 256GB', Quantity: 1 },
    { OrderItemId: `other-${id}`, ProductVariantId: 'another-product-variant', ProductName: 'Sản phẩm khác', VariantInfo: '512GB', Quantity: 1 }], ...overrides,
})

function mockApi({ reviews: initialReviews = [], orders = [order()], writeError, holdWrite = false, listError = false, summaryError = false, orderError = false } = {}) {
  const calls = []
  let reviews = [...initialReviews], releaseWrite
  const writeGate = new Promise((resolve) => { releaseWrite = resolve })
  const controls = { listError, summaryError, orderError, writeError }
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost')
    const path = url.pathname.replace(/^\/api/, '')
    const method = options.method || 'GET'
    const query = Object.fromEntries(url.searchParams)
    const body = options.body ? JSON.parse(options.body) : undefined
    calls.push({ path, method, query, params: url.searchParams, body, token: options.headers?.Authorization })
    let data, status = 200
    if (path === '/products/p1/reviews') {
      const items = reviews.filter((item) => !query.rating || item.Rating === Number(query.rating))
      const page = Number(query.page), size = Number(query.page_size)
      if ((size === 1 && controls.summaryError) || (size !== 1 && controls.listError)) {
        status = 503; data = { detail: 'Không thể tải đánh giá lúc này.' }
      } else data = { Items: items.slice((page - 1) * size, page * size), Total: items.length, Page: page, PageSize: size }
    } else if (path === '/orders') {
      const page = Number(query.page), size = Number(query.page_size)
      if (controls.orderError) { status = 503; data = { detail: 'Không tải được đơn hàng.' } }
      else data = { Items: orders.slice((page - 1) * size, page * size), Total: orders.length, Page: page, PageSize: size }
    } else if (path.startsWith('/orders/')) data = orders.find((item) => item.OrderId === path.split('/')[2])
    else if (path === '/reviews' || (path.startsWith('/reviews/') && method === 'PATCH')) {
      if (holdWrite) await writeGate
      if (controls.writeError) { status = controls.writeError.status; data = controls.writeError.body }
      else if (method === 'POST') {
        data = review('new', body.Rating, 'Customer-id', { Content: body.Content, CreatedAt: new Date(NOW).toISOString() })
        reviews.unshift(data); status = 201
      } else {
        reviews = reviews.map((item) => item.ReviewId === path.split('/')[2] ? { ...item, ...body } : item)
        data = reviews.find((item) => item.ReviewId === path.split('/')[2])
      }
    } else { status = 404; data = { detail: 'Không tìm thấy dữ liệu.' } }
    return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
  }))
  return { calls, controls, releaseWrite }
}

function show({ role = 'Customer', onRequireLogin = vi.fn(), onSummaryChange = vi.fn(), url = '/san-pham/demo' } = {}) {
  render(<MemoryRouter initialEntries={[url]}><AuthContext.Provider value={makeAuth({ role })}>
    <div className="pd-page"><ProductReviews product={product} onRequireLogin={onRequireLogin} onSummaryChange={onSummaryChange} /></div>
  </AuthContext.Provider></MemoryRouter>)
  return { onRequireLogin, onSummaryChange }
}

async function openComposer(user) {
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  const dialog = screen.getByRole('dialog', { name: 'Viết đánh giá' })
  await within(dialog).findByText(/Đơn hàng VT-/)
  await user.click(within(dialog).getByRole('radio', { name: '5 sao', exact: true }))
  await user.type(within(dialog).getByRole('textbox', { name: 'Nhận xét của bạn' }), '  Sản phẩm dùng rất tốt.  ')
  return dialog
}

beforeEach(() => vi.spyOn(Date, 'now').mockReturnValue(NOW))
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

test('guests read reviews without tokens or private order requests; writing uses the existing login prompt', async () => {
  const { calls } = mockApi({ reviews: [review('a')] })
  const { onRequireLogin } = show({ role: null })
  expect(await screen.findByText('Nội dung đánh giá a')).toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  expect(onRequireLogin).toHaveBeenCalledOnce()
  expect(calls.every((call) => call.path === '/products/p1/reviews' && !call.token)).toBe(true)
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
})

test.each(['Staff', 'Admin'])('%s cannot open a customer review composer', async (role) => {
  const { calls } = mockApi(); const { onRequireLogin } = show({ role })
  await userEvent.setup().click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  expect(onRequireLogin).toHaveBeenCalledOnce()
  expect(calls.some((call) => call.path === '/orders')).toBe(false)
})

test('the histogram counts all pages, load more appends reviews, and a star filter starts a fresh list', async () => {
  const reviews = Array.from({ length: 12 }, (_, index) => review(String(index), index < 10 ? 5 : 2))
  const { calls } = mockApi({ reviews }); const { onSummaryChange } = show(); const user = userEvent.setup()
  await screen.findByText('Nội dung đánh giá 0')
  expect(await screen.findByRole('button', { name: 'Lọc 5 sao, 10 đánh giá' })).toBeInTheDocument()
  expect(onSummaryChange).toHaveBeenLastCalledWith(expect.objectContaining({ count: 12, rating: 4.5 }))
  expect(screen.getAllByRole('article')).toHaveLength(3)
  await user.click(screen.getByRole('button', { name: 'Xem thêm đánh giá' }))
  expect(await screen.findByText('Nội dung đánh giá 5')).toBeInTheDocument()
  expect(screen.getByText('Nội dung đánh giá 0')).toBeInTheDocument()
  expect(screen.getAllByRole('article')).toHaveLength(6)
  expect(calls.some((call) => call.query.page === '2' && call.query.page_size === '3')).toBe(true)
  await user.click(within(screen.getByRole('group', { name: 'Lọc đánh giá theo số sao' })).getByRole('button', { name: '2', exact: true }))
  expect(await screen.findByText('Nội dung đánh giá 10')).toBeInTheDocument()
  expect(screen.getAllByRole('article')).toHaveLength(2)
  expect(calls.at(-1).query).toMatchObject({ rating: '2', page: '1', page_size: '3' })
  expect(screen.queryByRole('button', { name: 'Xem thêm đánh giá' })).not.toBeInTheDocument()
})

test('a failed load more keeps earlier reviews and retry appends once until all reviews are visible', async () => {
  const { controls } = mockApi({ reviews: Array.from({ length: 7 }, (_, index) => review(String(index))) })
  show(); const user = userEvent.setup()
  await screen.findByText('Nội dung đánh giá 0')
  controls.listError = true
  await user.click(screen.getByRole('button', { name: 'Xem thêm đánh giá' }))
  const alert = await screen.findByRole('alert')
  expect(screen.getAllByRole('article')).toHaveLength(3)
  controls.listError = false
  await user.click(within(alert).getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Nội dung đánh giá 5')
  expect(screen.getAllByRole('article')).toHaveLength(6)
  await user.click(screen.getByRole('button', { name: 'Xem thêm đánh giá' }))
  await screen.findByText('Nội dung đánh giá 6')
  expect(screen.getAllByRole('article')).toHaveLength(7)
  expect(screen.queryByRole('button', { name: 'Xem thêm đánh giá' })).not.toBeInTheDocument()
})

test('switching star filters during load more discards the late page and preserves only matching reviews', async () => {
  mockApi({ reviews: Array.from({ length: 8 }, (_, index) => review(String(index), index < 6 ? 5 : 2)) })
  const fetch = globalThis.fetch
  let release
  const gate = new Promise(resolve => { release = resolve })
  vi.stubGlobal('fetch', vi.fn(async (input, options) => {
    const url = new URL(input, 'http://localhost')
    if (url.searchParams.get('page') === '2') await gate
    return fetch(input, options)
  }))
  show(); const user = userEvent.setup()
  await screen.findByText('Nội dung đánh giá 0')
  await user.click(screen.getByRole('button', { name: 'Xem thêm đánh giá' }))
  expect(screen.getAllByRole('article')).toHaveLength(3)
  expect(screen.getByRole('button', { name: 'Xem thêm đánh giá' })).toBeDisabled()
  await user.click(within(screen.getByRole('group', { name: 'Lọc đánh giá theo số sao' })).getByRole('button', { name: '2', exact: true }))
  await screen.findByText('Nội dung đánh giá 6')
  await act(async () => release())
  expect(screen.getAllByRole('article')).toHaveLength(2)
  expect(screen.queryByText('Nội dung đánh giá 0')).not.toBeInTheDocument()
})

test('a failed list remains retryable and is never presented as an empty review list', async () => {
  const { controls } = mockApi({ listError: true, reviews: [review('a')] }); show()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Không thể tải đánh giá')
  expect(screen.queryByText('Chưa có đánh giá ở đây')).not.toBeInTheDocument()
  controls.listError = false
  await userEvent.setup().click(within(alert).getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText('Nội dung đánh giá a')).toBeInTheDocument()
})

test('summary failure preserves the readable review list and can be retried separately', async () => {
  const { controls } = mockApi({ summaryError: true, reviews: [review('a')] }); show()
  expect(await screen.findByText('Nội dung đánh giá a')).toBeInTheDocument()
  expect(await screen.findByText('Không tải được thống kê đánh giá.')).toBeInTheDocument()
  controls.summaryError = false
  await userEvent.setup().click(screen.getByRole('button', { name: 'Tải lại thống kê' }))
  expect(await screen.findByRole('button', { name: 'Lọc 5 sao, 1 đánh giá' })).toBeInTheDocument()
})

test('an empty filter invites a different filter without fabricating reviews', async () => {
  mockApi({ reviews: [review('a')] }); show(); const user = userEvent.setup()
  await screen.findByText('Nội dung đánh giá a')
  await user.click(within(screen.getByRole('group', { name: 'Lọc đánh giá theo số sao' })).getByRole('button', { name: '1', exact: true }))
  expect(await screen.findByText('Chưa có đánh giá 1 sao')).toBeInTheDocument()
  expect(screen.queryByRole('article')).not.toBeInTheDocument()
})

test('creation sends only the purchased line, stars and trimmed content, then refreshes reviews and statistics', async () => {
  const { calls } = mockApi(); const { onSummaryChange } = show(); const user = userEvent.setup()
  const dialog = await openComposer(user)
  // The review is for this product: no order or version to pick, only the purchase it is tied to.
  expect(within(dialog).queryByRole('combobox')).not.toBeInTheDocument()
  expect(within(dialog).getByText(product.Name, { exact: true })).toBeInTheDocument()
  expect(within(dialog).getByText(/Đơn hàng VT-/)).toHaveTextContent('Đen · 256GB')
  expect(within(dialog).queryByText(/Sản phẩm khác/)).not.toBeInTheDocument()
  await user.click(within(dialog).getByRole('button', { name: 'Gửi đánh giá' }))
  expect(await screen.findByText('Sản phẩm dùng rất tốt.')).toBeInTheDocument()
  await waitFor(() => expect(onSummaryChange).toHaveBeenLastCalledWith(expect.objectContaining({ count: 1, rating: 5 })))
  const write = calls.find((call) => call.method === 'POST')
  expect(write).toMatchObject({ path: '/reviews', token: 'Bearer access-for-test', body: { OrderItemId: 'item-o1', Rating: 5, Content: 'Sản phẩm dùng rất tốt.' } })
  expect(Object.keys(write.body).sort()).toEqual(['Content', 'OrderItemId', 'Rating'])
  // Received orders (Delivered or Completed) that hold this product.
  const orders = calls.find((call) => call.path === '/orders').params
  expect([orders.getAll('order_status'), orders.get('product_id')]).toEqual([['Delivered', 'Completed'], product.ProductId])
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Xóa đánh giá/ })).not.toBeInTheDocument()
})

test('a customer without delivered orders cannot send a review', async () => {
  const { calls } = mockApi({ orders: [] }); show(); const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  expect(await screen.findByText(/Bạn chưa có đơn hàng đã giao/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gửi đánh giá' })).toBeDisabled()
  expect(calls.some((call) => call.method === 'POST')).toBe(false)
})

test('an order load error remains retryable instead of saying the customer has no purchases', async () => {
  const { controls } = mockApi({ orderError: true }); show(); const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Không tải được đơn hàng.')
  expect(screen.queryByText(/Bạn chưa có đơn hàng đã giao/)).not.toBeInTheDocument()
  controls.orderError = false
  await user.click(within(alert).getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText(/Đơn hàng VT-/)).toBeInTheDocument()
})

test('a completed order can be reviewed: the review goes to its line of this product', async () => {
  const { calls } = mockApi({ orders: [order('o1', { OrderStatus: 'Completed' })] }); show(); const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  const dialog = screen.getByRole('dialog', { name: 'Viết đánh giá' })
  await within(dialog).findByText(/Đơn hàng VT-/)
  await user.click(within(dialog).getByRole('radio', { name: '4 sao', exact: true }))
  await user.type(within(dialog).getByRole('textbox', { name: 'Nhận xét của bạn' }), 'Dùng ổn định.')
  await user.click(within(dialog).getByRole('button', { name: 'Gửi đánh giá' }))
  await waitFor(() => expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ OrderItemId: 'item-o1', Rating: 4, Content: 'Dùng ổn định.' }))
})
test('opened from an order (?review=), the form opens at once and the review goes to that purchase', async () => {
  const { calls } = mockApi({ orders: [order('o1'), order('o2')] })
  show({ url: '/san-pham/demo?review=o2' }); const user = userEvent.setup()

  const dialog = await screen.findByRole('dialog', { name: 'Viết đánh giá' })
  await within(dialog).findByText(/Đơn hàng VT-/)
  await user.click(within(dialog).getByRole('radio', { name: '5 sao', exact: true }))
  await user.type(within(dialog).getByRole('textbox', { name: 'Nhận xét của bạn' }), 'Giao nhanh.')
  await user.click(within(dialog).getByRole('button', { name: 'Gửi đánh giá' }))
  await waitFor(() => expect(calls.find((call) => call.method === 'POST')?.body.OrderItemId).toBe('item-o2'))
})

test('every purchase already reviewed: nothing to send, and the form says so', async () => {
  const reviewed = (id) => order(id, { Items: [{ OrderItemId: `item-${id}`, ProductVariantId: 'v1', ProductId: product.ProductId,
    ProductName: product.Name, VariantInfo: 'Đen · 256GB', Quantity: 1, ReviewId: `r-${id}` }] })
  const { calls } = mockApi({ orders: [reviewed('o1'), reviewed('o2')] }); show(); const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  await waitFor(() => expect(screen.queryByText('Đang kiểm tra sản phẩm bạn đã mua…')).not.toBeInTheDocument())
  expect(screen.queryByText('Bạn đã đánh giá sản phẩm này cho mọi lần mua.')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gửi đánh giá' })).toBeDisabled()
  expect(calls.some((call) => call.method === 'POST')).toBe(false)
})
test.each(['Shipping', 'Cancelled'])('a stale order detail at %s cannot be reviewed', async (status) => {
  const { calls } = mockApi({ orders: [order('o1', { OrderStatus: status })] }); show(); const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  expect(await screen.findByText(/Bạn chưa có đơn hàng đã giao nào có sản phẩm này/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gửi đánh giá' })).toBeDisabled()
  expect(calls.some((call) => call.method === 'POST')).toBe(false)
})

test('a purchase of an inactive variant still counts, and later pages are read when the newest are reviewed', async () => {
  const orders = Array.from({ length: 51 }, (_, index) => order(`o${index + 1}`, {
    Items: [{ OrderItemId: `line${index}`, ProductVariantId: index === 50 ? 'old-variant' : 'v1', ProductName: product.Name,
      VariantInfo: 'Phiên bản đã mua', Quantity: 1, ReviewId: index === 50 ? null : `r${index}` }],
  }))
  const { calls } = mockApi({ orders }); show(); const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  const dialog = screen.getByRole('dialog', { name: 'Viết đánh giá' })
  await within(dialog).findByText(/Đơn hàng VT-/)
  expect(calls.some((call) => call.path === '/orders' && call.query.page === '2')).toBe(true)
  await user.click(within(dialog).getByRole('radio', { name: '3 sao', exact: true }))
  await user.type(within(dialog).getByRole('textbox', { name: 'Nhận xét của bạn' }), 'Bản cũ vẫn tốt.')
  await user.click(within(dialog).getByRole('button', { name: 'Gửi đánh giá' }))
  await waitFor(() => expect(calls.find((call) => call.method === 'POST')?.body.OrderItemId).toBe('line50'))
})
test('missing stars and whitespace content are rejected without sending a review', async () => {
  const { calls } = mockApi(); show(); const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Viết đánh giá' }))
  await screen.findByText(/Đơn hàng VT-/)
  await user.type(screen.getByRole('textbox', { name: 'Nhận xét của bạn' }), '   ')
  await user.click(screen.getByRole('button', { name: 'Gửi đánh giá' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Vui lòng chọn số sao')
  await user.click(screen.getByRole('radio', { name: '4 sao', exact: true }))
  await user.click(screen.getByRole('button', { name: 'Gửi đánh giá' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Nội dung đánh giá không được để trống.')
  expect(calls.some((call) => call.method === 'POST')).toBe(false)
})

test.each([
  [409, 'review_exists', 'Dòng đơn hàng đã được đánh giá'],
  [400, 'review_order_not_delivered', 'Chỉ đánh giá sản phẩm thuộc đơn hàng đã giao'],
  [403, null, 'Bạn không có quyền thực hiện thao tác này.'],
  [401, null, 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'],
])('write failure %s retains the form and shows the backend rule', async (status, code, detail) => {
  mockApi({ writeError: { status, body: { code, detail } } }); show(); const user = userEvent.setup()
  const dialog = await openComposer(user)
  await user.click(within(dialog).getByRole('button', { name: 'Gửi đánh giá' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(detail)
  expect(within(dialog).getByRole('textbox', { name: 'Nhận xét của bạn' })).toHaveValue('  Sản phẩm dùng rất tốt.  ')
  // Reviewed meanwhile: the next purchase is looked up; here there is none left.
  if (code === 'review_exists') {
    await waitFor(() => expect(within(dialog).queryByText('Đang kiểm tra sản phẩm bạn đã mua…')).not.toBeInTheDocument())
    expect(within(dialog).queryByText('Bạn đã đánh giá sản phẩm này cho mọi lần mua.')).not.toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Gửi đánh giá' })).toBeDisabled()
  }
})

test('repeated clicks and closing during a pending write never send a second review', async () => {
  const { calls, releaseWrite } = mockApi({ holdWrite: true }); show(); const user = userEvent.setup()
  const dialog = await openComposer(user)
  const submit = within(dialog).getByRole('button', { name: 'Gửi đánh giá' })
  fireEvent.click(submit); fireEvent.click(submit)
  await waitFor(() => expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1))
  await user.click(within(dialog).getByRole('button', { name: 'Đóng cửa sổ' }))
  expect(dialog).toBeInTheDocument()
  await act(async () => releaseWrite())
  expect(await screen.findByText('Sản phẩm dùng rất tốt.')).toBeInTheDocument()
})

test('only the owner within seven days sees edit; editing changes stars/content without selecting a new order', async () => {
  const own = review('own', 5, 'Customer-id')
  const expired = review('expired', 3, 'Customer-id', { CreatedAt: new Date(NOW - REVIEW_EDIT_WINDOW_MS).toISOString() })
  const { calls } = mockApi({ reviews: [own, expired, review('other')] }); show(); const user = userEvent.setup()
  await screen.findByText('Nội dung đánh giá own')
  expect(screen.getAllByRole('button', { name: 'Chỉnh sửa đánh giá' })).toHaveLength(1)
  await user.click(screen.getByRole('button', { name: 'Chỉnh sửa đánh giá' }))
  const dialog = screen.getByRole('dialog', { name: 'Sửa đánh giá' })
  expect(within(dialog).queryByRole('combobox')).not.toBeInTheDocument()
  await user.click(within(dialog).getByRole('radio', { name: '4 sao', exact: true }))
  const text = within(dialog).getByRole('textbox', { name: 'Nhận xét của bạn' })
  await user.clear(text); await user.type(text, 'Nội dung đã cập nhật')
  await user.click(within(dialog).getByRole('button', { name: 'Cập nhật đánh giá' }))
  expect(await screen.findByText('Nội dung đã cập nhật')).toBeInTheDocument()
  expect(calls.find((call) => call.method === 'PATCH')).toMatchObject({ path: '/reviews/own', body: { Rating: 4, Content: 'Nội dung đã cập nhật' } })
  expect(calls.some((call) => call.path === '/orders')).toBe(false)
})

test('the exact edit deadline is excluded, invalid dates and another customer cannot edit', () => {
  const created = NOW - REVIEW_EDIT_WINDOW_MS
  const own = review('own', 5, 'Customer-id', { CreatedAt: new Date(created).toISOString() })
  expect(canEditReview(own, 'Customer-id', NOW - 1)).toBe(true)
  expect(canEditReview(own, 'Customer-id', NOW)).toBe(false)
  expect(canEditReview(own, 'other-user', NOW - 1)).toBe(false)
  expect(canEditReview({ ...own, CreatedAt: 'invalid' }, 'Customer-id', NOW - 1)).toBe(false)
})

test('the submit rechecks a deadline that expires while the form is open', async () => {
  const own = review('own', 5, 'Customer-id')
  const { calls } = mockApi({ reviews: [own] }); show(); const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Chỉnh sửa đánh giá' }))
  vi.mocked(Date.now).mockReturnValue(Date.parse(own.CreatedAt) + REVIEW_EDIT_WINDOW_MS)
  await user.click(screen.getByRole('button', { name: 'Cập nhật đánh giá' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Đã quá thời hạn 7 ngày')
  expect(calls.some((call) => call.method === 'PATCH')).toBe(false)
})

test('review text remains plain text and existing photos open a preview; unsafe image URLs are omitted', async () => {
  mockApi({ reviews: [review('images', 5, 'other-user', { Content: '<script>window.reviewExecuted = true</script>',
    Images: [{ ReviewImageId: 'img1', ImageUrl: '/review-photo.png', DisplayOrder: 0 },
      { ReviewImageId: 'img2', ImageUrl: 'javascript:alert(1)', DisplayOrder: 1 }] })] }); show(); const user = userEvent.setup()
  expect(await screen.findByText('<script>window.reviewExecuted = true</script>')).toBeInTheDocument()
  expect(window.reviewExecuted).toBeUndefined()
  expect(screen.getAllByRole('button', { name: /Phóng to ảnh đánh giá/ })).toHaveLength(1)
  await user.click(screen.getByRole('button', { name: 'Phóng to ảnh đánh giá 1' }))
  expect(within(screen.getByRole('dialog', { name: 'Ảnh đánh giá sản phẩm' })).getByRole('img')).toHaveAttribute('src', '/review-photo.png')
})
