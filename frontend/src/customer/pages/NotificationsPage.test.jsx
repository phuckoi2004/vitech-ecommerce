import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { appRoutes } from '../../routes.jsx'
import { makeAuth } from '../../test/auth.js'

const id = '11111111-1111-4111-8111-111111111111'
const notice = { NotificationId: 'note-1', Title: 'Thông báo đơn hàng', Content: 'Đơn hàng đã được cập nhật.', NotificationType: 'Order', ReferenceType: 'Order', ReferenceId: id, ActionUrl: null, IsRead: false, CreatedAt: '2026-10-16T08:00:00Z' }
function mockApi(notes = [{ ...notice }]) {
  const state = { notes, failCount: false, failList: false, failMark: false, failDetail: false, calls: [] }
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost'), path = url.pathname.replace(/^\/api/, ''), method = options.method || 'GET'
    state.calls.push({ path, method, query: url.searchParams })
    let data
    if (path === '/users/me/notifications/unread-count') {
      if (state.failCount) return json({ detail: 'Không tải được số chưa đọc.' }, 503)
      data = { Count: state.notes.filter(item => !item.IsRead).length }
    } else if (path === '/users/me/notifications') {
      if (state.failList) return json({ detail: 'Không tải được danh sách.' }, 503)
      const page = Number(url.searchParams.get('page') || 1)
      data = { Items: state.notes.slice((page - 1) * 20, page * 20), Total: state.notes.length, Page: page, PageSize: 20 }
    } else if (path.startsWith('/users/me/notifications/') && method === 'POST') {
      if (state.failMark) return json({ detail: 'Không lưu được trạng thái đã đọc.' }, 503)
      if (path.endsWith('/read-all')) {
        const unread = state.notes.filter(item => !item.IsRead)
        unread.forEach(item => { item.IsRead = true }); data = { Count: unread.length }
      } else { data = state.notes.find(item => path.includes('/' + item.NotificationId + '/')); data.IsRead = true }
    } else if (path === '/orders/' + id) {
      if (state.failDetail) return json({ detail: 'Không tìm thấy đơn hàng' }, 404)
      data = { OrderId: id, OrderCode: 'VT-001', OrderStatus: 'Shipping', PaymentStatus: 'Paid', TotalAmount: '100000', ReceiverName: 'Khách thử', ShippingAddress: 'Hà Nội', OrderedAt: notice.CreatedAt, InternalNote: 'PRIVATE-INTERNAL', Items: [{ OrderItemId: 'item-1', ProductName: 'Sản phẩm đã mua', VariantInfo: 'Đen · 256GB', Quantity: 1, LineTotal: '100000', UnitCost: 'PRIVATE-COST' }], StatusHistories: [] }
    } else if (path === '/warranty-requests/' + id) data = { RequestCode: 'BH-001', Status: 'Processing', RequestedAt: notice.CreatedAt, IssueDescription: 'Máy không lên nguồn', ResultType: 'Repaired', ResultNote: 'PRIVATE-UNAPPROVED', ResultApprovedAt: null, Histories: [] }
    else if (path === '/return-requests/' + id) data = { RequestCode: 'DT-001', Status: 'Pending', RequestedAt: notice.CreatedAt, Reason: 'Sản phẩm lỗi màn hình', Histories: [] }
    else if (['/categories', '/brands', '/banners'].includes(path)) data = []
    else data = { Items: [], Total: 0, SelectedQuantity: 0, SelectedSubtotal: '0' }
    return json(data)
  }))
  return state
}
function json(data, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }) }
function renderPage() {
  const router = createMemoryRouter(appRoutes, { initialEntries: ['/thong-bao'] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Customer' })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

test('foreground polling updates both the notification list and bell after thirty seconds', async () => {
  vi.useFakeTimers()
  const state = mockApi([])
  await act(async () => { renderPage() })
  expect(screen.getByRole('heading', { name: 'Chưa có thông báo' })).toBeInTheDocument()
  state.notes.push({ ...notice })
  await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
  expect(screen.getByRole('button', { name: notice.Title, exact: true })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Thông báo.*1 chưa đọc/ })).toBeInTheDocument()
})

test('returning to the page refreshes new notifications and reads made on another device', async () => {
  const state = mockApi([])
  renderPage()
  await screen.findByRole('heading', { name: 'Chưa có thông báo' })
  state.notes.push({ ...notice })
  await act(async () => window.dispatchEvent(new Event('focus')))
  expect(await screen.findByRole('button', { name: notice.Title, exact: true })).toBeInTheDocument()
  expect(await screen.findByRole('link', { name: /Thông báo.*1 chưa đọc/ })).toBeInTheDocument()
  state.notes[0].IsRead = true
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  expect(await screen.findByRole('link', { name: 'Thông báo', exact: true })).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Đánh dấu đã đọc', exact: true })).not.toBeInTheDocument())
})

test('hidden tabs do not request notifications and resume when visible again', async () => {
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
  const state = mockApi()
  renderPage()
  expect(state.calls.filter(call => call.path.includes('/notifications'))).toHaveLength(0)
  hidden.mockReturnValue(false)
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  expect(await screen.findByRole('button', { name: notice.Title, exact: true })).toBeInTheDocument()
  expect(await screen.findByRole('link', { name: /Thông báo.*1 chưa đọc/ })).toBeInTheDocument()
})

test('marking read during an older list request refreshes again instead of keeping stale unread data', async () => {
  mockApi()
  renderPage()
  await screen.findByRole('button', { name: notice.Title, exact: true })
  const fetchApi = globalThis.fetch
  let release, intercepted = false
  vi.stubGlobal('fetch', vi.fn((input, options) => {
    const url = new URL(input, 'http://localhost')
    if (url.pathname === '/api/users/me/notifications' && !intercepted) {
      intercepted = true
      return new Promise(resolve => { release = () => resolve(json({ Items: [{ ...notice }], Total: 1, Page: 1, PageSize: 20 })) })
    }
    return fetchApi(input, options)
  }))
  await act(async () => window.dispatchEvent(new Event('focus')))
  await userEvent.setup().click(screen.getByRole('button', { name: 'Đánh dấu đã đọc', exact: true }))
  await screen.findByRole('link', { name: 'Thông báo', exact: true })
  await act(async () => release())
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Đánh dấu đã đọc', exact: true })).not.toBeInTheDocument())
})

test('a count failure is visible, retains the previous unread count and has a working retry', async () => {
  const state = mockApi()
  renderPage()
  await screen.findByRole('link', { name: /Thông báo.*1 chưa đọc/ })
  state.failCount = true
  await act(async () => window.dispatchEvent(new Event('focus')))
  const error = await screen.findByRole('alert', { name: 'Không cập nhật được thông báo' })
  expect(screen.getByRole('link', { name: /Thông báo.*1 chưa đọc/ })).toBeInTheDocument()
  state.failCount = false
  state.notes[0].IsRead = true
  await userEvent.setup().click(within(error).getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByRole('link', { name: 'Thông báo', exact: true })).toBeInTheDocument()
  expect(screen.queryByRole('alert', { name: 'Không cập nhật được thông báo' })).not.toBeInTheDocument()
})

test('initial list and count failures stay distinguishable from an empty inbox', async () => {
  const state = mockApi()
  state.failList = true; state.failCount = true
  renderPage()
  await screen.findByRole('heading', { name: 'Không cập nhật được danh sách thông báo' })
  expect(screen.getByRole('alert', { name: 'Không cập nhật được thông báo' })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Chưa có thông báo' })).not.toBeInTheDocument()
  state.failList = false; state.failCount = false
  await act(async () => window.dispatchEvent(new Event('focus')))
  expect(await screen.findByRole('button', { name: notice.Title, exact: true })).toBeInTheDocument()
})

test.each([
  ['Order', '/orders/', 'Chi tiết đơn hàng', 'VT-001'],
  ['WarrantyRequest', '/warranty-requests/', 'Chi tiết bảo hành', 'BH-001'],
  ['ReturnRequest', '/return-requests/', 'Chi tiết đổi trả', 'DT-001'],
])('opens %s using only the existing customer API and marks the notification read', async (type, path, title, code) => {
  const state = mockApi([{ ...notice, ReferenceType: type }])
  renderPage()
  await userEvent.setup().click(await screen.findByRole('button', { name: notice.Title, exact: true }))
  const dialog = await screen.findByRole('dialog', { name: title })
  expect(await within(dialog).findByText(code)).toBeInTheDocument()
  expect(state.notes[0].IsRead).toBe(true)
  expect(state.calls.some(call => call.path === path + id)).toBe(true)
  expect(state.calls.some(call => call.path.startsWith('/admin/'))).toBe(false)
  expect(screen.queryByText(/PRIVATE-/)).not.toBeInTheDocument()
  // Only an order links to its own page (payment status and, while awaited, the transfer QR).
  const orderLink = within(dialog).queryByRole('link', { name: 'Mở trang đơn hàng' })
  if (type === 'Order') expect(orderLink).toHaveAttribute('href', `/don-hang/${id}`)
  else expect(orderLink).not.toBeInTheDocument()
})

test('a failed read action remains retryable and opens its original content after retry', async () => {
  const state = mockApi()
  state.failMark = true
  renderPage()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: notice.Title, exact: true }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Không lưu được trạng thái đã đọc.')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  state.failMark = false
  await user.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByRole('dialog', { name: 'Chi tiết đơn hàng' })).toBeInTheDocument()
  expect(state.notes[0].IsRead).toBe(true)
})

test('duplicate read clicks send a single write and read-all covers every page', async () => {
  const state = mockApi(Array.from({ length: 21 }, (_, index) => ({ ...notice, NotificationId: 'note-' + index, Title: 'Thông báo ' + index })))
  renderPage()
  const first = (await screen.findAllByRole('button', { name: 'Đánh dấu đã đọc', exact: true }))[0]
  fireEvent.click(first); fireEvent.click(first)
  await waitFor(() => expect(state.notes[0].IsRead).toBe(true))
  expect(state.calls.filter(call => call.method === 'POST')).toHaveLength(1)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Sau', exact: true }))
  await screen.findByText('Thông báo 20', { exact: true })
  await user.click(screen.getByRole('button', { name: 'Đánh dấu tất cả đã đọc' }))
  await waitFor(() => expect(state.notes.every(item => item.IsRead)).toBe(true))
  expect(await screen.findByRole('link', { name: 'Thông báo', exact: true })).toBeInTheDocument()
})

test('missing or foreign content shows a retryable error instead of another resource', async () => {
  const state = mockApi()
  state.failDetail = true
  renderPage()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: notice.Title, exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'Chi tiết đơn hàng' })
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Không tìm thấy đơn hàng')
  state.failDetail = false
  await user.click(within(dialog).getByRole('button', { name: 'Thử lại' }))
  expect(await within(dialog).findByText('VT-001')).toBeInTheDocument()
})
