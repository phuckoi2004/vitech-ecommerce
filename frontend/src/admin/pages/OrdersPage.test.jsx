import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'
import OrdersPage from './OrdersPage.jsx'
import OrderDetailPage from './OrderDetailPage.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), updateOrderStatus: vi.fn(), confirmCodDelivery: vi.fn(), updateOrderNote: vi.fn(), assignOrderSerials: vi.fn(), releaseOrderSerial: vi.fn() }))
// The breadcrumb test lands on the dashboard, which loads stock and revenue through these two reads.
const dashboard = vi.hoisted(() => ({ getDashboardStock: vi.fn(), getRevenueSeries: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData, ...dashboard }))
vi.mock('../services/orders.js', () => api)

const permissions = ['admin.portal', 'orders:view', 'orders:update']
const base = {
  AssignedStaffId: 'Staff-id', OrderId: 'o1', OrderCode: 'DH-THAT-01', ReceiverName: 'Người mua từ API', ReceiverPhone: '0912345678',
  OrderedAt: '2026-10-02T18:00:00Z', OrderStatus: 'Pending', PaymentStatus: 'Pending', PaymentMethodId: 'pm1',
  ShippingAddress: 'Địa chỉ từ API', CustomerNote: 'Gọi trước khi giao', InternalNote: 'Đóng gói cẩn thận', CancelReason: null,
  Subtotal: '2000000.00', ShippingFee: '30000.00', DiscountAmount: '100000.00', TotalAmount: '1930000.00',
  Items: [{ OrderItemId: 'item1', ProductVariantId: 'v1', ProductName: 'Điện thoại từ API', Sku: 'PHONE-DEN', VariantInfo: 'Màu đen / 128GB', Quantity: 1, UnitPrice: '2000000.00', DiscountAmount: '0.00', LineTotal: '2000000.00' }],
  StatusHistories: [{ OrderStatusHistoryId: 'h1', OldStatus: null, NewStatus: 'Pending', Note: 'Lịch sử từ API', ChangedAt: '2026-10-02T18:00:00Z' }],
}
let orders, method, serialItems

function renderPage(path = '/admin/orders', granted = permissions, routes, role = 'Staff') {
  const router = createMemoryRouter(routes ?? [{ path: '/admin/orders', element: <OrdersPage /> }, { path: '/admin/orders/:orderId', element: <OrderDetailPage /> }], { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

beforeEach(() => {
  vi.resetAllMocks()
  orders = []
  method = { PaymentMethodId: 'pm1', Code: 'COD', Name: 'Thanh toán khi nhận hàng', IsActive: false }
  serialItems = [{ OrderItemId: 'item1', ProductVariantId: 'v1', Sku: 'PHONE-DEN', Quantity: 1, IsSerialTracked: true, SerialNumbers: [] }]
  dashboard.getDashboardStock.mockResolvedValue({ Items: [], Total: 0 })
  dashboard.getRevenueSeries.mockImplementation(async (_, months) => months.map((month) => ({ month, data: { NetRevenue: '0.00', OrderCount: 0 }, error: '' })))
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/statistics/orders') return { TotalOrders: orders.length, ByStatus: {} }
    if (path === '/admin/orders') {
      const filtered = orders.filter((order) => (!query.keyword || order.OrderCode.includes(query.keyword)) && (!query.order_status || order.OrderStatus === query.order_status))
      return { Items: filtered.slice((query.page - 1) * query.page_size, query.page * query.page_size), Total: filtered.length, Page: query.page, PageSize: query.page_size }
    }
    if (path === '/payment-methods/pm1') return { ...method }
    if (path === '/admin/orders/o1/serials') return structuredClone(serialItems)
    const order = orders.find((item) => path === '/admin/orders/' + item.OrderId)
    if (order) return structuredClone(order)
    throw new Error('Không tìm thấy đơn hàng.')
  })
  api.updateOrderStatus.mockImplementation(async (_, id, body) => {
    orders = orders.map((item) => item.OrderId === id ? { ...item, OrderStatus: body.OrderStatus } : item)
    return orders.find((item) => item.OrderId === id)
  })
  api.confirmCodDelivery.mockImplementation(async (_, id) => {
    orders = orders.map((item) => item.OrderId === id ? { ...item, OrderStatus: 'Delivered', PaymentStatus: 'Paid' } : item)
    return orders.find((item) => item.OrderId === id)
  })
  api.updateOrderNote.mockImplementation(async (_, id, body) => {
    orders = orders.map((item) => item.OrderId === id ? { ...item, ...body } : item)
    return orders.find((item) => item.OrderId === id)
  })
  api.assignOrderSerials.mockImplementation(async (_, __, body) => {
    serialItems = serialItems.map((item) => ({ ...item, SerialNumbers: [...item.SerialNumbers, ...body.Items[0].SerialNumbers] }))
    return structuredClone(serialItems)
  })
  api.releaseOrderSerial.mockImplementation(async (_, __, number) => {
    serialItems = serialItems.map((item) => ({ ...item, SerialNumbers: item.SerialNumbers.filter((value) => value !== number) }))
    return structuredClone(serialItems)
  })
})

test('empty data retains the seven Figma headers, zero count and no example orders', async () => {
  renderPage()
  await screen.findByText('Chưa có đơn hàng.')
  for (const name of ['Mã đơn', 'Khách hàng', 'SĐT', 'Ngày đặt', 'Trạng thái', 'Bước tiếp theo', 'Thao tác']) expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
  expect(screen.getByText('0 đơn hàng')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 đơn hàng')).toBeInTheDocument()
  expect(screen.queryByText('DH-1028')).not.toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/orders', { page: 1, page_size: 5, keyword: '', order_status: '' }, expect.any(AbortSignal))
})

test('search starts from one character and sends a contiguous phone fragment without submitting', async () => {
  orders = [{ ...base }]
  renderPage()
  await screen.findByText('1 đơn hàng')
  const input = screen.getByRole('searchbox')
  for (const keyword of ['0', '098', 'An']) {
    fireEvent.change(input, { target: { value: keyword } })
    await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/orders',
      { page: 1, page_size: 5, keyword, order_status: '' }, expect.any(AbortSignal)))
  }
})

test('another staff member can view an order but cannot invoke its next step', async () => {
  orders = [{ ...base, OrderStatus: 'Processing', AssignedStaffId: 'another-staff' }]
  renderPage('/admin/orders?order=o1&action=advance')
  const dialog = await screen.findByRole('dialog', { name: 'Chi tiết đơn hàng' })
  await within(dialog).findByText('Địa chỉ từ API')
  expect(within(dialog).queryByRole('button', { name: /Giao hàng|Hủy đơn hàng|Lưu ghi chú/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Giao hàng DH-THAT-01' })).not.toBeInTheDocument()
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
})

test('an Admin can act on an order owned by another staff member', async () => {
  orders = [{ ...base, OrderStatus: 'Processing', AssignedStaffId: 'another-staff' }]
  renderPage('/admin/orders?order=o1&action=advance', permissions, undefined, 'Admin')
  const dialog = await screen.findByRole('dialog', { name: 'Cập nhật trạng thái đơn hàng' })
  await within(dialog).findByText('Địa chỉ từ API')
  expect(within(dialog).getByRole('button', { name: 'Giao hàng', exact: true })).toBeInTheDocument()
})

test('typing searches a code, status filters reach the server and browser history restores controls', async () => {
  orders = [{ ...base }, { ...base, OrderId: 'o2', OrderCode: 'DH-THAT-02', OrderStatus: 'Processing' }]
  const router = renderPage('/admin/orders?page=2')
  await screen.findByText('2 đơn hàng')
  const search = screen.getByRole('searchbox', { name: 'Tìm kiếm đơn hàng theo mã, tên tài khoản hoặc số điện thoại' })
  fireEvent.change(search, { target: { value: 'THAT-02' } })
  expect(screen.queryByRole('button', { name: 'Tìm kiếm', exact: true })).not.toBeInTheDocument()
  await screen.findByText('1 đơn hàng')
  expect(router.state.location.search).toBe('?keyword=THAT-02')
  fireEvent.click(screen.getByRole('button', { name: 'Đang xử lý', exact: true }))
  await waitFor(() => expect(api.getAdminData).toHaveBeenLastCalledWith('access-for-test', '/admin/orders', { page: 1, page_size: 5, keyword: 'THAT-02', order_status: 'Processing' }, expect.any(AbortSignal)))
  expect(screen.getByRole('button', { name: 'Đang xử lý', exact: true })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'Đã giao', exact: true }))
  await screen.findByText('Không có đơn hàng phù hợp.')
  await act(() => router.navigate(-1))
  await screen.findByText('DH-THAT-02')
  expect(search).toHaveValue('THAT-02')
  expect(screen.getByRole('button', { name: 'Đang xử lý', exact: true })).toHaveAttribute('aria-pressed', 'true')
})

test('Vietnamese composition waits until finished and rapid typing sends only the final search', async () => {
  orders = [{ ...base }]
  const router = renderPage()
  await screen.findByText('1 đơn hàng')
  const search = screen.getByRole('searchbox')
  fireEvent.compositionStart(search)
  fireEvent.change(search, { target: { value: 'TH' } })
  fireEvent.change(search, { target: { value: 'THAT' } })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 450)) })
  expect(router.state.location.search).toBe('')
  fireEvent.compositionEnd(search)
  await waitFor(() => expect(router.state.location.search).toBe('?keyword=THAT'))
  expect(api.getAdminData.mock.calls.filter((call) => call[1] === '/admin/orders' && call[2].keyword === 'THAT')).toHaveLength(1)
})

test('navigation cancels an unfinished search and restores URL-backed input', async () => {
  orders = [{ ...base }]
  const router = renderPage()
  await screen.findByText('1 đơn hàng')
  const search = screen.getByRole('searchbox')
  fireEvent.change(search, { target: { value: 'unfinished' } })
  await act(async () => router.navigate('/admin/orders?status=Processing'))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 450)) })
  expect(router.state.location.search).toBe('?status=Processing')
  expect(search).toHaveValue('')
  expect(api.getAdminData.mock.calls.some((call) => call[1] === '/admin/orders' && call[2].keyword === 'unfinished')).toBe(false)
})

test('server pagination uses five records and clamps a now-empty deep page', async () => {
  orders = Array.from({ length: 7 }, (_, index) => ({ ...base, OrderId: 'page-' + index, OrderCode: 'DH-' + index }))
  const router = renderPage('/admin/orders?page=99')
  await waitFor(() => expect(router.state.location.search).toBe('?page=2'))
  await screen.findByText('Hiển thị 6–7 trong 7 đơn hàng')
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(3)
  fireEvent.click(screen.getByRole('button', { name: 'Trang trước' }))
  await screen.findByText('Hiển thị 1–5 trong 7 đơn hàng')
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(6)
})

test('filter changes hide old rows immediately and errors are distinct from an empty list', async () => {
  orders = [{ ...base }]
  renderPage()
  await screen.findByText(base.OrderCode)
  api.getAdminData.mockImplementationOnce(() => new Promise(() => {}))
  fireEvent.click(screen.getByRole('button', { name: 'Đang giao', exact: true }))
  expect(screen.queryByText(base.OrderCode)).not.toBeInTheDocument()
  api.getAdminData.mockRejectedValueOnce(new Error('Không kết nối được máy chủ.'))
  fireEvent.click(screen.getByRole('button', { name: 'Đã giao', exact: true }))
  await screen.findByText('Không kết nối được máy chủ.')
  expect(screen.queryByText('0 đơn hàng')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Không có đơn hàng phù hợp.')
})

test('the detail link opens a separate page and back retains the list filters', async () => {
  orders = [{ ...base }]
  const router = renderPage('/admin/orders?keyword=THAT')
  fireEvent.click(await screen.findByRole('button', { name: 'Xem chi tiết DH-THAT-01' }))
  const page = await screen.findByRole('region', { name: 'Chi tiết đơn hàng' })
  await within(page).findByText('SKU: PHONE-DEN')
  expect(within(page).getByText('Màu đen / 128GB')).toBeInTheDocument()
  expect(within(page).getByText('Địa chỉ từ API')).toBeInTheDocument()
  expect(within(page).getByText('01:00 03/10/2026')).toBeInTheDocument()
  expect(within(page).getByText(/1\.930\.000/)).toBeInTheDocument()
  expect(within(page).getByText('Lịch sử từ API')).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/admin/orders/o1')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
  fireEvent.click(within(page).getByRole('button', { name: '← Quay lại' }))
  expect(router.state.location.pathname).toBe('/admin/orders')
  expect(router.state.location.search).toBe('?keyword=THAT')
})

test.each([['Pending', 'Processing', 'Xác nhận'], ['Processing', 'Shipping', 'Giao hàng']])('advancing %s requires confirmation and sends only the next state', async (current, target, label) => {
  orders = [{ ...base, OrderStatus: current }]
  serialItems[0].SerialNumbers = ['SN-PACKED']
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: label + ' DH-THAT-01' }))
  const dialog = await screen.findByRole('dialog', { name: 'Cập nhật trạng thái đơn hàng' })
  await within(dialog).findByText('Địa chỉ từ API')
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Ghi chú xử lý' }), { target: { value: 'Đã kiểm tra' } })
  fireEvent.click(within(dialog).getByRole('button', { name: label, exact: true }))
  await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: target, Note: 'Đã kiểm tra' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(orders[0].OrderStatus).toBe(target)
})

test.each(['Staff', 'Admin'])('old stock without codes can ship while serials stay read only for %s', async (role) => {
  orders = [{ ...base, OrderStatus: 'Processing' }]
  renderPage('/admin/orders', permissions, undefined, role)
  fireEvent.click(await screen.findByRole('button', { name: 'Giao hàng DH-THAT-01' }))
  const dialog = await screen.findByRole('dialog', { name: 'Cập nhật trạng thái đơn hàng' })
  const label = await within(dialog).findByText('Serial/IMEI:')
  expect(label.nextElementSibling).toBeEmptyDOMElement()
  expect(within(dialog).getByRole('button', { name: 'Giao hàng', exact: true })).toBeEnabled()
  expect(within(dialog).queryByRole('textbox', { name: /Serial/ })).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: /Gán mã|Gỡ Serial/ })).not.toBeInTheDocument()
  expect(api.assignOrderSerials).not.toHaveBeenCalled()
  expect(api.releaseOrderSerial).not.toHaveBeenCalled()
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
})

test('an unpaid online payment cannot ship even after serial requirements are satisfied', async () => {
  orders = [{ ...base, OrderStatus: 'Processing' }]
  method = { ...method, Code: 'SEPAY', Name: 'Chuyển khoản' }
  serialItems[0].SerialNumbers = ['SN-01']
  renderPage('/admin/orders?order=o1&action=advance')
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Đơn thanh toán trực tuyến phải được thanh toán trước khi giao hàng.')
  expect(within(dialog).getByRole('button', { name: 'Giao hàng', exact: true })).toBeDisabled()
  fireEvent.submit(dialog.querySelector('#order-status-form'))
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
})

test('an unpaid transfer order cannot be confirmed from the quick action; the dialog says why', async () => {
  method = { ...method, Code: 'SEPAY', Name: 'Chuyển khoản' }
  orders = [{ ...base }]
  renderPage('/admin/orders?order=o1&action=advance')
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Đơn thanh toán chuyển khoản chỉ được xác nhận sau khi khách đã thanh toán (hiện tại: Chưa thanh toán).')
  expect(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })).toBeDisabled()
  fireEvent.submit(dialog.querySelector('#order-status-form'))
  expect(api.updateOrderStatus).not.toHaveBeenCalled()

  // Back on the details, the confirm action itself is disabled and points to the reason.
  fireEvent.click(within(dialog).getByRole('button', { name: 'Quay lại chi tiết' }))
  const action = within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })
  expect(action).toBeDisabled()
  expect(action).toHaveAccessibleDescription('Đơn thanh toán chuyển khoản chỉ được xác nhận sau khi khách đã thanh toán (hiện tại: Chưa thanh toán).')
  expect(within(dialog).getByRole('button', { name: 'Hủy đơn hàng' })).toBeEnabled()
})

test('a paid transfer order is confirmed from the quick action as before', async () => {
  method = { ...method, Code: 'SEPAY', Name: 'Chuyển khoản' }
  orders = [{ ...base, PaymentStatus: 'Paid' }]
  renderPage('/admin/orders?order=o1&action=advance')
  const dialog = await screen.findByRole('dialog')
  const confirm = within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })
  await waitFor(() => expect(confirm).toBeEnabled())
  expect(within(dialog).queryByText(/chỉ được xác nhận sau khi khách đã thanh toán/)).not.toBeInTheDocument()
  fireEvent.click(confirm)
  await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: 'Processing', Note: null }))
})

test('COD delivery requires explicit collection and uses the collection endpoint without a client amount', async () => {
  orders = [{ ...base, OrderStatus: 'Shipping' }]
  renderPage('/admin/orders?order=o1&action=advance')
  const dialog = await screen.findByRole('dialog')
  const collected = await within(dialog).findByRole('checkbox', { name: /Tôi xác nhận đã giao hàng thành công/ })
  const confirm = within(dialog).getByRole('button', { name: 'Xác nhận giao và thu tiền' })
  expect(confirm).toBeDisabled()
  fireEvent.click(collected)
  fireEvent.click(confirm)
  await waitFor(() => expect(api.confirmCodDelivery).toHaveBeenCalledWith('access-for-test', 'o1', { Note: null }))
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(orders[0].PaymentStatus).toBe('Paid')
})

test('paid online delivery uses a normal status change, and failed payment metadata must be retried first', async () => {
  orders = [{ ...base, OrderStatus: 'Shipping', PaymentStatus: 'Paid' }]
  method.Code = 'SEPAY'
  const original = api.getAdminData.getMockImplementation()
  let fail = true
  api.getAdminData.mockImplementation((token, path, query) => path === '/payment-methods/pm1' && fail ? Promise.reject(new Error('Lỗi tải phương thức thanh toán.')) : original(token, path, query))
  renderPage('/admin/orders?order=o1&action=advance')
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Lỗi tải phương thức thanh toán.')
  expect(within(dialog).getByRole('button', { name: 'Giao hoàn tất' })).toBeDisabled()
  fail = false
  fireEvent.click(within(dialog).getByRole('button', { name: 'Thử lại' }))
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Giao hoàn tất' })).toBeEnabled())
  fireEvent.click(within(dialog).getByRole('button', { name: 'Giao hoàn tất' }))
  await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: 'Delivered', Note: null }))
  expect(api.confirmCodDelivery).not.toHaveBeenCalled()
})

test('cancelling an in-transit paid order explains stock and refunds, requires a reason and preserves filters', async () => {
  orders = [{ ...base, OrderStatus: 'Shipping', PaymentStatus: 'Paid' }]
  const router = renderPage('/admin/orders?status=Shipping&order=o1')
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Hủy đơn hàng' }))
  expect(within(dialog).getByText(/tồn kho chưa được hoàn ngay/)).toBeInTheDocument()
  expect(within(dialog).getByText(/cần xử lý hoàn tiền/)).toBeInTheDocument()
  const confirm = within(dialog).getByRole('button', { name: 'Xác nhận hủy đơn' })
  expect(confirm).toBeDisabled()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Lý do hủy' }), { target: { value: 'Khách từ chối nhận' } })
  fireEvent.click(confirm)
  await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: 'Cancelled', CancelReason: 'Khách từ chối nhận', Note: null }))
  await screen.findByText('Không có đơn hàng phù hợp.')
  expect(router.state.location.search).toBe('?status=Shipping')
})

test('internal-note edits can clear the value and do not modify assignment, payment or receiver information', async () => {
  orders = [{ ...base }]
  renderPage('/admin/orders?order=o1')
  const dialog = await screen.findByRole('dialog')
  const note = await within(dialog).findByRole('textbox', { name: 'Ghi chú nội bộ' })
  expect(within(dialog).getByRole('button', { name: 'Lưu ghi chú' })).toBeDisabled()
  fireEvent.change(note, { target: { value: '' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Lưu ghi chú' }))
  await waitFor(() => expect(api.updateOrderNote).toHaveBeenCalledWith('access-for-test', 'o1', { InternalNote: null }))
  expect(await within(dialog).findByRole('textbox', { name: 'Ghi chú nội bộ' })).toHaveValue('')
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Lưu ghi chú' })).toBeDisabled())
})

test('write failures retain notes for retry and a pending write disables duplicate confirmation and closing', async () => {
  orders = [{ ...base }]
  api.updateOrderStatus.mockRejectedValueOnce(new Error('Đơn hàng vừa được cập nhật.'))
  renderPage('/admin/orders?order=o1&action=advance')
  const dialog = await screen.findByRole('dialog')
  const note = await within(dialog).findByRole('textbox', { name: 'Ghi chú xử lý' })
  fireEvent.change(note, { target: { value: 'Ghi chú cần giữ' } })
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Xác nhận', exact: true }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Đơn hàng vừa được cập nhật.')
  expect(note).toHaveValue('Ghi chú cần giữ')
  let finish
  api.updateOrderStatus.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Xác nhận', exact: true }))
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Đang cập nhật…' })).toBeDisabled())
  expect(within(dialog).getByRole('button', { name: 'Đóng' })).toBeDisabled()
  fireEvent.submit(dialog.querySelector('#order-status-form'))
  expect(api.updateOrderStatus).toHaveBeenCalledTimes(2)
  await act(async () => finish({ ...base, OrderStatus: 'Processing' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

test('fresh detail determines the next state even if the list row is stale', async () => {
  orders = [{ ...base }]
  const original = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation((token, path, query) => path === '/admin/orders/o1' ? Promise.resolve({ ...base, OrderStatus: 'Delivered' }) : original(token, path, query))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận DH-THAT-01' }))
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Địa chỉ từ API')
  expect(within(dialog).queryByRole('button', { name: /Xác nhận|Giao hàng|Giao hoàn tất|Hoàn tất/ })).not.toBeInTheDocument()
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
})

test('view-only sessions cannot open write actions through direct query parameters', async () => {
  orders = [{ ...base, OrderStatus: 'Processing' }]
  renderPage('/admin/orders?order=o1&action=advance', ['admin.portal', 'orders:view'])
  const dialog = await screen.findByRole('dialog', { name: 'Chi tiết đơn hàng' })
  await within(dialog).findByText('Địa chỉ từ API')
  await within(dialog).findByText('Serial/IMEI:')
  expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: /Gán mã|Hủy đơn|Giao hàng|Lưu ghi chú/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Giao hàng DH-THAT-01' })).not.toBeInTheDocument()
  for (const write of [api.assignOrderSerials, api.updateOrderStatus, api.updateOrderNote, api.confirmCodDelivery]) expect(write).not.toHaveBeenCalled()
})

test.each(['Cancelled', 'Delivered', 'Completed'])('terminal %s orders have no next-state or cancel button', async (status) => {
  orders = [{ ...base, OrderStatus: status }]
  renderPage('/admin/orders?order=o1')
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Địa chỉ từ API')
  expect(within(dialog).queryByRole('button', { name: /Hủy đơn hàng|Xác nhận|Hoàn tất|Giao hàng/ })).not.toBeInTheDocument()
})

test('the actual route displays the order page and header; the breadcrumb returns to dashboard', async () => {
  orders = [{ ...base }]
  const router = renderPage('/admin/orders', permissions, adminRoutes)
  expect(await screen.findByRole('heading', { level: 1, name: 'Quản lý đơn hàng' })).toBeInTheDocument()
  await screen.findByRole('button', { name: 'Xem chi tiết DH-THAT-01' })
  expect(screen.getByRole('button', { name: 'Đơn hàng', exact: true })).toHaveAttribute('aria-current', 'page')
  fireEvent.click(within(screen.getByRole('banner')).getByRole('button', { name: 'Trang chủ' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/admin'))
})

test('the route denies sessions without orders:view before reading order data', async () => {
  renderPage('/admin/orders', ['admin.portal'], adminRoutes)
  await screen.findByText('Không có quyền truy cập')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/orders'))).toBe(false)
})
