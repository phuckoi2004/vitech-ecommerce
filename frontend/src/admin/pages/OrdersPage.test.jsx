import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'
import OrdersPage from './OrdersPage.jsx'
import OrderDetailPage from './OrderDetailPage.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), updateOrderStatus: vi.fn(), confirmCodDelivery: vi.fn(), updateOrderNote: vi.fn(), assignOrderSerials: vi.fn(), releaseOrderSerial: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData,
  getDashboardStock: async () => ({ Items: [], Total: 0 }), getRevenueSeries: async () => [],
}))
vi.mock('../services/orders.js', () => api)

const permissions = ['admin.portal', 'orders:view', 'orders:update']
const base = {
  OrderId: 'o1', OrderCode: 'DH-THAT-01', ReceiverName: 'Người mua từ API', ReceiverPhone: '0912345678',
  OrderedAt: '2026-10-02T18:00:00Z', OrderStatus: 'Pending', PaymentStatus: 'Pending', PaymentMethodId: 'pm1',
  ShippingAddress: 'Địa chỉ từ API', CustomerNote: 'Gọi trước khi giao', InternalNote: 'Đóng gói cẩn thận', CancelReason: null,
  Subtotal: '2000000.00', ShippingFee: '30000.00', DiscountAmount: '100000.00', TotalAmount: '1930000.00',
  Items: [{ OrderItemId: 'item1', ProductVariantId: 'v1', ProductName: 'Điện thoại từ API', Sku: 'PHONE-DEN', VariantInfo: 'Màu đen / 128GB', Quantity: 1, UnitPrice: '2000000.00', DiscountAmount: '0.00', LineTotal: '2000000.00' }],
  StatusHistories: [{ OrderStatusHistoryId: 'h1', OldStatus: null, NewStatus: 'Pending', Note: 'Lịch sử từ API', ChangedAt: '2026-10-02T18:00:00Z' }],
}
let orders, method, serialItems

function renderPage(path = '/admin/orders', granted = permissions, routes) {
  const router = createMemoryRouter(routes ?? [{ path: '/admin/orders', element: <OrdersPage /> }, { path: '/admin/orders/:orderId', element: <OrderDetailPage /> }], { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Staff', permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

beforeEach(() => {
  vi.resetAllMocks()
  orders = []
  method = { PaymentMethodId: 'pm1', Code: 'COD', Name: 'Thanh toán khi nhận hàng', IsActive: false }
  serialItems = [{ OrderItemId: 'item1', ProductVariantId: 'v1', Sku: 'PHONE-DEN', Quantity: 1, IsSerialTracked: true, SerialNumbers: [] }]
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/orders') {
      const filtered = orders.filter((order) => (!query.order_code || order.OrderCode.includes(query.order_code)) && (!query.order_status || order.OrderStatus === query.order_status))
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
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/orders', { page: 1, page_size: 5, order_code: '', order_status: '' }, expect.any(AbortSignal))
})

test('typing searches a code, status filters reach the server and browser history restores controls', async () => {
  orders = [{ ...base }, { ...base, OrderId: 'o2', OrderCode: 'DH-THAT-02', OrderStatus: 'Confirmed' }]
  const router = renderPage('/admin/orders?page=2')
  await screen.findByText('2 đơn hàng')
  const search = screen.getByRole('searchbox', { name: 'Tìm kiếm đơn hàng theo mã' })
  fireEvent.change(search, { target: { value: 'THAT-02' } })
  expect(screen.queryByRole('button', { name: 'Tìm kiếm', exact: true })).not.toBeInTheDocument()
  await screen.findByText('1 đơn hàng')
  expect(router.state.location.search).toBe('?keyword=THAT-02')
  fireEvent.click(screen.getByRole('button', { name: 'Đã xác nhận', exact: true }))
  await waitFor(() => expect(api.getAdminData).toHaveBeenLastCalledWith('access-for-test', '/admin/orders', { page: 1, page_size: 5, order_code: 'THAT-02', order_status: 'Confirmed' }, expect.any(AbortSignal)))
  expect(screen.getByRole('button', { name: 'Đã xác nhận', exact: true })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'Hoàn tất', exact: true }))
  await screen.findByText('Không có đơn hàng phù hợp.')
  await act(() => router.navigate(-1))
  await screen.findByText('DH-THAT-02')
  expect(search).toHaveValue('THAT-02')
  expect(screen.getByRole('button', { name: 'Đã xác nhận', exact: true })).toHaveAttribute('aria-pressed', 'true')
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
  expect(api.getAdminData.mock.calls.filter((call) => call[1] === '/admin/orders' && call[2].order_code === 'THAT')).toHaveLength(1)
})

test('navigation cancels an unfinished search and restores URL-backed input', async () => {
  orders = [{ ...base }]
  const router = renderPage()
  await screen.findByText('1 đơn hàng')
  const search = screen.getByRole('searchbox')
  fireEvent.change(search, { target: { value: 'unfinished' } })
  await act(async () => router.navigate('/admin/orders?status=Confirmed'))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 450)) })
  expect(router.state.location.search).toBe('?status=Confirmed')
  expect(search).toHaveValue('')
  expect(api.getAdminData.mock.calls.some((call) => call[1] === '/admin/orders' && call[2].order_code === 'unfinished')).toBe(false)
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

test.each([['Pending', 'Confirmed', 'Xác nhận đơn'], ['Confirmed', 'Processing', 'Bắt đầu xử lý'], ['Delivered', 'Completed', 'Hoàn tất']])('advancing %s requires confirmation and sends only the next state', async (current, target, label) => {
  orders = [{ ...base, OrderStatus: current }]
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: label + ' DH-THAT-01' }))
  const dialog = screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn hàng' })
  await within(dialog).findByText('Địa chỉ từ API')
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Ghi chú xử lý' }), { target: { value: 'Đã kiểm tra' } })
  fireEvent.click(within(dialog).getByRole('button', { name: label, exact: true }))
  await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: target, Note: 'Đã kiểm tra' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(orders[0].OrderStatus).toBe(target)
})

test('packing requires real serials, rejects duplicates and permits shipping only once all are assigned', async () => {
  orders = [{ ...base, OrderStatus: 'Processing' }]
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Chuyển đang giao DH-THAT-01' }))
  const dialog = screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn hàng' })
  const input = await within(dialog).findByRole('textbox', { name: 'Serial/IMEI cho PHONE-DEN' })
  const next = within(dialog).getByRole('button', { name: 'Chuyển đang giao', exact: true })
  expect(next).toBeDisabled()
  fireEvent.change(input, { target: { value: 'SN-01\nsn-01' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Gán mã' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('bị trùng')
  expect(api.assignOrderSerials).not.toHaveBeenCalled()
  fireEvent.change(input, { target: { value: 'SN-THAT-01' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Gán mã' }))
  await waitFor(() => expect(api.assignOrderSerials).toHaveBeenCalledWith('access-for-test', 'o1', { Items: [{ OrderItemId: 'item1', SerialNumbers: ['SN-THAT-01'] }] }))
  await waitFor(() => expect(next).toBeEnabled())
  fireEvent.click(within(dialog).getByRole('button', { name: 'Gỡ Serial/IMEI SN-THAT-01' }))
  await waitFor(() => expect(next).toBeDisabled())
  expect(api.releaseOrderSerial).toHaveBeenCalledWith('access-for-test', 'o1', 'SN-THAT-01')
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
})

test('an unpaid online payment cannot ship even after serial requirements are satisfied', async () => {
  orders = [{ ...base, OrderStatus: 'Processing' }]
  method = { ...method, Code: 'SEPAY', Name: 'Chuyển khoản' }
  serialItems[0].SerialNumbers = ['SN-01']
  renderPage('/admin/orders?order=o1&action=advance')
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Đơn thanh toán trực tuyến phải được thanh toán trước khi giao hàng.')
  expect(within(dialog).getByRole('button', { name: 'Chuyển đang giao', exact: true })).toBeDisabled()
  fireEvent.submit(dialog.querySelector('#order-status-form'))
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
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
  expect(within(dialog).getByRole('button', { name: 'Xác nhận đã giao' })).toBeDisabled()
  fail = false
  fireEvent.click(within(dialog).getByRole('button', { name: 'Thử lại' }))
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Xác nhận đã giao' })).toBeEnabled())
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận đã giao' }))
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
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận đơn', exact: true }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Đơn hàng vừa được cập nhật.')
  expect(note).toHaveValue('Ghi chú cần giữ')
  let finish
  api.updateOrderStatus.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận đơn', exact: true }))
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Đang cập nhật…' })).toBeDisabled())
  expect(within(dialog).getByRole('button', { name: 'Đóng' })).toBeDisabled()
  fireEvent.submit(dialog.querySelector('#order-status-form'))
  expect(api.updateOrderStatus).toHaveBeenCalledTimes(2)
  await act(async () => finish({ ...base, OrderStatus: 'Confirmed' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

test('fresh detail determines the next state even if the list row is stale', async () => {
  orders = [{ ...base }]
  const original = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation((token, path, query) => path === '/admin/orders/o1' ? Promise.resolve({ ...base, OrderStatus: 'Delivered' }) : original(token, path, query))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận đơn DH-THAT-01' }))
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Hoàn tất', exact: true }))
  await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: 'Completed', Note: null }))
})

test('view-only sessions cannot open write actions through direct query parameters', async () => {
  orders = [{ ...base, OrderStatus: 'Processing' }]
  renderPage('/admin/orders?order=o1&action=advance', ['admin.portal', 'orders:view'])
  const dialog = await screen.findByRole('dialog', { name: 'Chi tiết đơn hàng' })
  await within(dialog).findByText('Địa chỉ từ API')
  await within(dialog).findByText('Chưa gán Serial/IMEI.')
  expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: /Gán mã|Hủy đơn|Chuyển đang giao|Lưu ghi chú/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Chuyển đang giao DH-THAT-01' })).not.toBeInTheDocument()
  for (const write of [api.assignOrderSerials, api.updateOrderStatus, api.updateOrderNote, api.confirmCodDelivery]) expect(write).not.toHaveBeenCalled()
})

test.each(['Cancelled', 'Completed'])('terminal %s orders have no next-state or cancel button', async (status) => {
  orders = [{ ...base, OrderStatus: status }]
  renderPage('/admin/orders?order=o1')
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByText('Địa chỉ từ API')
  expect(within(dialog).queryByRole('button', { name: /Hủy đơn hàng|Xác nhận|Hoàn tất|Chuyển đang giao/ })).not.toBeInTheDocument()
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
