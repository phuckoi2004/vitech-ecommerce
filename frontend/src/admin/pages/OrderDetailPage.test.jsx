import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), updateOrderStatus: vi.fn(), confirmCodDelivery: vi.fn(), updateOrderNote: vi.fn(), assignOrderSerials: vi.fn(), releaseOrderSerial: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ getAdminData: api.getAdminData }))
vi.mock('../services/orders.js', () => api)

const permissions = ['admin.portal', 'orders:view', 'orders:update']
const base = {
  AssignedStaffId: 'Staff-id', OrderId: 'o1', OrderCode: 'DH-API-01', ReceiverName: 'Người nhận từ API', ReceiverPhone: '0912345678',
  OrderedAt: '2026-10-02T18:00:00Z', OrderStatus: 'Pending', PaymentStatus: 'Pending', PaymentMethodId: 'pm1',
  ShippingAddress: 'Địa chỉ giao hàng từ API', CustomerNote: 'Gọi trước khi giao', InternalNote: 'Ghi chú cần giữ',
  Subtotal: '2000000.00', ShippingFee: '30000.00', DiscountAmount: '100000.00', TotalAmount: '1930000.00',
  Items: [
    { OrderItemId: 'item1', ProductVariantId: 'v1', ProductName: 'Điện thoại', Sku: 'PHONE-DEN', VariantInfo: 'Màu đen', Quantity: 1, UnitPrice: '1000000.00', DiscountAmount: '0.00', LineTotal: '1000000.00' },
    { OrderItemId: 'item2', ProductVariantId: 'v2', ProductName: 'Điện thoại', Sku: 'PHONE-TRANG', VariantInfo: 'Màu trắng', Quantity: 1, UnitPrice: '1000000.00', DiscountAmount: '0.00', LineTotal: '1000000.00' },
  ],
  StatusHistories: [{ OrderStatusHistoryId: 'h1', OldStatus: null, NewStatus: 'Pending', Note: 'Sự kiện thật từ API', ChangedAt: '2026-10-02T18:00:00Z' }],
}
let order, method, serialItems

function renderPage(path = '/admin/orders/o1', granted = permissions) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Staff', permissions: granted })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

beforeEach(() => {
  vi.resetAllMocks()
  order = structuredClone(base)
  method = { PaymentMethodId: 'pm1', Code: 'COD', Name: 'Thanh toán khi nhận hàng' }
  serialItems = [{ OrderItemId: 'item1', Sku: 'PHONE-DEN', Quantity: 1, IsSerialTracked: true, SerialNumbers: [] }]
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/orders') return { Items: [], Total: 0 }
    if (path === '/admin/orders/' + order.OrderId) return structuredClone(order)
    if (path === '/admin/orders/' + order.OrderId + '/serials') return structuredClone(serialItems)
    if (path === '/payment-methods/pm1') return { ...method }
    throw new Error('Không tìm thấy đơn hàng.')
  })
  api.updateOrderStatus.mockImplementation(async (_, __, body) => {
    order = { ...order, OrderStatus: body.OrderStatus, CancelReason: body.CancelReason ?? null,
      StatusHistories: [...order.StatusHistories, { OrderStatusHistoryId: 'h2', OldStatus: order.OrderStatus, NewStatus: body.OrderStatus, Note: body.Note, ChangedAt: '2026-10-14T06:00:00Z' }],
    }
    return structuredClone(order)
  })
  api.confirmCodDelivery.mockImplementation(async () => {
    order = { ...order, OrderStatus: 'Delivered', PaymentStatus: 'Paid' }
    return structuredClone(order)
  })
  api.updateOrderNote.mockImplementation(async (_, __, body) => { order = { ...order, ...body }; return structuredClone(order) })
  api.assignOrderSerials.mockImplementation(async (_, __, body) => {
    serialItems = serialItems.map((item) => ({ ...item, SerialNumbers: body.Items[0].SerialNumbers }))
    return structuredClone(serialItems)
  })
})

test.each([['Pending', 'Chưa thanh toán'], ['Failed', 'Thanh toán thất bại']])(
  'a transfer order with payment %s cannot be confirmed: the action is disabled with the reason', async (status, label) => {
    method = { PaymentMethodId: 'pm1', Code: 'SEPAY', Name: 'Chuyển khoản QR' }
    order = { ...order, PaymentStatus: status }
    renderPage()
    const confirm = await screen.findByRole('button', { name: 'Xác nhận', exact: true }, { timeout: 5000 })
    await waitFor(() => expect(confirm).toBeDisabled())
    expect(confirm).toHaveAccessibleDescription(`Đơn thanh toán chuyển khoản chỉ được xác nhận sau khi khách đã thanh toán (hiện tại: ${label}).`)
    fireEvent.click(confirm)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.updateOrderStatus).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Hủy đơn' })).toBeEnabled() // cancelling stays available
  })

test.each([['a paid transfer order', 'SEPAY', 'Paid'], ['an unpaid COD order', 'COD', 'Pending']])(
  '%s is confirmed as before', async (_, code, paymentStatus) => {
    method = { PaymentMethodId: 'pm1', Code: code, Name: code }
    order = { ...order, PaymentStatus: paymentStatus }
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận', exact: true }))
    const dialog = screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn hàng' })
    const submit = within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })
    await waitFor(() => expect(submit).toBeEnabled())
    expect(screen.queryByText(/chỉ được xác nhận sau khi khách đã thanh toán/)).not.toBeInTheDocument()
    fireEvent.click(submit)
    await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: 'Processing', Note: null }))
  })

test('while its payment method cannot be read, an order is not confirmed', async () => {
  const answer = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation(async (token, path, ...rest) => path === '/payment-methods/pm1'
    ? Promise.reject(new Error('Lỗi tải phương thức thanh toán.')) : answer(token, path, ...rest))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận', exact: true }))
  const dialog = screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn hàng' })
  expect(await within(dialog).findByText('Lỗi tải phương thức thanh toán.')).toBeInTheDocument()
  expect(within(dialog).getByText('Cần tải được phương thức thanh toán trước khi xác nhận đơn.')).toBeInTheDocument()
  expect(within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })).toBeDisabled()
  fireEvent.submit(dialog.querySelector('#order-status-form'))
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
})

test('the full route renders Figma sections, live breadcrumb and active orders menu without a detail modal', async () => {
  renderPage()
  await screen.findByRole('heading', { level: 2, name: 'Đơn hàng #DH-API-01' })
  expect(screen.getByRole('heading', { level: 1, name: 'Chi tiết đơn hàng' })).toBeInTheDocument()
  for (const name of ['Thông tin đơn hàng', 'Sản phẩm trong đơn', 'Lịch sử trạng thái', 'Cập nhật trạng thái']) expect(screen.getByRole('heading', { name })).toBeInTheDocument()
  expect(await within(screen.getByRole('banner')).findByText('/ DH-API-01')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Đơn hàng', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  const logo = document.querySelector('aside img[src*="order-logo"]')
  expect(logo).toHaveAttribute('width', '93')
  expect(logo).toHaveAttribute('height', '57')
  expect(screen.getByRole('region', { name: 'Lịch sử trạng thái' }).querySelectorAll('img')).toHaveLength(1)
  expect(api.getAdminData.mock.calls.some(([, path]) => path === '/admin/orders')).toBe(false)
})

test('different variants remain separate product rows; history contains only events actually returned', async () => {
  renderPage()
  const table = await screen.findByRole('table')
  expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Sản phẩm', 'SL', 'Đơn giá', 'Thành tiền'])
  expect(within(table).getAllByRole('row')).toHaveLength(3)
  expect(within(table).getByText('SKU: PHONE-DEN')).toBeInTheDocument()
  expect(within(table).getByText('SKU: PHONE-TRANG')).toBeInTheDocument()
  const history = screen.getByRole('region', { name: 'Lịch sử trạng thái' })
  expect(within(history).getByText('Sự kiện thật từ API')).toBeInTheDocument()
  expect(within(history).getByText('01:00 03/10/2026')).toBeInTheDocument()
  expect(screen.queryByText(/Hệ thống thông báo đơn mới/)).not.toBeInTheDocument()
})

test('empty product and history arrays keep the table headers without inventing records', async () => {
  order.Items = []; order.StatusHistories = []
  renderPage()
  await screen.findByText('Đơn hàng chưa có sản phẩm.')
  expect(screen.getAllByRole('columnheader')).toHaveLength(4)
  expect(screen.getByText('Chưa có lịch sử trạng thái.')).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Lịch sử trạng thái' }).querySelectorAll('img')).toHaveLength(0)
  expect(screen.queryByText('iPhone 17 Pro Max 256GB')).not.toBeInTheDocument()
})

test.each([['Pending', 0, 'Chờ xác nhận'], ['Confirmed', 0, 'Đã xác nhận'], ['Processing', 1, 'Đang xử lý'], ['Shipping', 2, 'Đang giao'], ['Delivered', 3, 'Đã giao'], ['Completed', 3, 'Hoàn tất']])('progress handles backend state %s within the four design stages', async (status, index, label) => {
  order.OrderStatus = status
  renderPage()
  const progress = await screen.findByRole('list', { name: 'Tiến trình đơn hàng' })
  const steps = within(progress).getAllByRole('listitem')
  expect(steps).toHaveLength(4)
  expect(steps[index]).toHaveAttribute('aria-current', 'step')
  expect(steps[index]).toHaveTextContent(label)
  expect(steps.filter((step) => step.getAttribute('aria-current') === 'step')).toHaveLength(1)
})

test('cancelled orders have no active delivery stage and no cancel or forward action', async () => {
  order.OrderStatus = 'Cancelled'
  renderPage()
  const progress = await screen.findByRole('list', { name: 'Tiến trình đơn hàng' })
  expect(progress.querySelector('[aria-current="step"]')).toBeNull()
  expect(screen.queryByRole('button', { name: /Hủy đơn|Xác nhận|Hoàn tất/ })).not.toBeInTheDocument()
  expect(screen.getByText('Đơn hàng đã đóng.')).toBeInTheDocument()
})

test('confirming updates the detail page, history and next action without returning to the list', async () => {
  const router = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận', exact: true }))
  const dialog = screen.getByRole('dialog', { name: 'Cập nhật trạng thái đơn hàng' })
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Ghi chú xử lý' }), { target: { value: 'Đã gọi xác nhận' } })
  const submit = within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })
  await waitFor(() => expect(submit).toBeEnabled())
  fireEvent.click(submit)
  await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: 'Processing', Note: 'Đã gọi xác nhận' }))
  await screen.findByRole('button', { name: 'Giao hàng' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByText('Đã gọi xác nhận')).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/admin/orders/o1')
})

test('packing displays system assigned serials read only and permits shipping', async () => {
  order.OrderStatus = 'Processing'
  serialItems[0].SerialNumbers = ['SERIAL-THAT']
  renderPage()
  await screen.findByText('SERIAL-THAT')
  expect(screen.queryByRole('textbox', { name: /Serial/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Gán mã|Gỡ Serial/ })).not.toBeInTheDocument()
  expect(api.assignOrderSerials).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Giao hàng' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Giao hàng' }))
  await waitFor(() => expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: 'Shipping', Note: null }))
  await screen.findByRole('button', { name: 'Giao hoàn tất' })
})

test('COD confirmation on the page requires collection and refreshes the payment state', async () => {
  order.OrderStatus = 'Shipping'
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Giao hoàn tất' }))
  const dialog = screen.getByRole('dialog')
  const checkbox = await within(dialog).findByRole('checkbox', { name: /Tôi xác nhận đã giao hàng thành công/ })
  const confirm = within(dialog).getByRole('button', { name: 'Xác nhận giao và thu tiền' })
  expect(confirm).toBeDisabled()
  fireEvent.click(checkbox); fireEvent.click(confirm)
  await waitFor(() => expect(api.confirmCodDelivery).toHaveBeenCalledWith('access-for-test', 'o1', { Note: null }))
  await screen.findByText('Đơn hàng đã hoàn tất.')
  expect(order.PaymentStatus).toBe('Paid')
  expect(api.updateOrderStatus).not.toHaveBeenCalled()
})

test('cancelling requires a reason and refreshes the page to a closed order', async () => {
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Hủy đơn', exact: true }))
  const dialog = screen.getByRole('dialog', { name: 'Hủy đơn hàng' })
  const confirm = within(dialog).getByRole('button', { name: 'Xác nhận hủy đơn' })
  expect(confirm).toBeDisabled()
  fireEvent.change(within(dialog).getByRole('textbox', { name: 'Lý do hủy' }), { target: { value: 'Khách đổi nhu cầu' } })
  fireEvent.click(confirm)
  await screen.findByText('Đơn hàng đã đóng.')
  expect(api.updateOrderStatus).toHaveBeenCalledWith('access-for-test', 'o1', { OrderStatus: 'Cancelled', CancelReason: 'Khách đổi nhu cầu', Note: null })
})

test('saving a cleared internal note preserves the expanded delivery panel after refresh', async () => {
  renderPage()
  fireEvent.click(await screen.findByText('Giao hàng, thanh toán & ghi chú'))
  const note = await screen.findByRole('textbox', { name: 'Ghi chú nội bộ' })
  expect(note).toHaveValue('Ghi chú cần giữ')
  fireEvent.change(note, { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu ghi chú' }))
  await waitFor(() => expect(api.updateOrderNote).toHaveBeenCalledWith('access-for-test', 'o1', { InternalNote: null }))
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Ghi chú nội bộ' })).toHaveValue(''))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Lưu ghi chú' })).toBeDisabled())
})

test('failed confirmation retains typed notes and can be dismissed without a second write', async () => {
  api.updateOrderStatus.mockRejectedValueOnce(new Error('Đơn đã thay đổi, vui lòng tải lại.'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận', exact: true }))
  const dialog = screen.getByRole('dialog')
  const note = within(dialog).getByRole('textbox', { name: 'Ghi chú xử lý' })
  fireEvent.change(note, { target: { value: 'Giữ ghi chú này' } })
  const submit = within(dialog).getByRole('button', { name: 'Xác nhận', exact: true })
  await waitFor(() => expect(submit).toBeEnabled())
  fireEvent.click(submit)
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Đơn đã thay đổi')
  expect(note).toHaveValue('Giữ ghi chú này')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Đóng' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(api.updateOrderStatus).toHaveBeenCalledTimes(1)
})

test('back from a direct detail link returns to a safe list URL with search, status and pagination', async () => {
  const original = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation((token, path, query) => path === '/admin/orders' ? Promise.resolve({ Items: [base], Total: 20 }) : original(token, path, query))
  const router = renderPage('/admin/orders/o1?keyword=DH&status=Pending&page=3&next=https%3A%2F%2Fevil.example&action=advance')
  await screen.findByText('Đơn hàng #DH-API-01')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '← Quay lại' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/admin/orders'))
  expect(router.state.location.search).toContain('keyword=DH')
  expect(router.state.location.search).toContain('status=Pending')
  expect(router.state.location.search).toContain('page=3')
  expect(router.state.location.search).not.toMatch(/next|action/)
})

test('read failures keep retry and back available; recovery never inserts Figma example data', async () => {
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((token, path, query) => path === '/admin/orders/o1' && failed ? Promise.reject(new Error('Không tìm thấy đơn hàng.')) : original(token, path, query))
  renderPage()
  await screen.findByText('Không tìm thấy đơn hàng.')
  expect(screen.getByRole('button', { name: '← Quay lại' })).toBeEnabled()
  expect(screen.queryByText('DH-1028')).not.toBeInTheDocument()
  failed = false
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('Đơn hàng #DH-API-01')
})

test('view-only sessions see the same detail page but cannot edit or mutate an order', async () => {
  order.OrderStatus = 'Processing'
  renderPage('/admin/orders/o1?action=advance', ['admin.portal', 'orders:view'])
  await screen.findByText('Đơn hàng #DH-API-01')
  await screen.findByText('Serial/IMEI:')
  expect(screen.queryByRole('button', { name: /Hủy đơn|Giao hàng|Gán mã/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('Giao hàng, thanh toán & ghi chú'))
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  for (const write of [api.updateOrderStatus, api.assignOrderSerials, api.updateOrderNote, api.confirmCodDelivery]) expect(write).not.toHaveBeenCalled()
})

test('missing orders:view denies a direct detail URL without reading the order', async () => {
  renderPage('/admin/orders/o1', ['admin.portal'])
  await screen.findByText('Không có quyền truy cập')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/orders'))).toBe(false)
})

test('changing order URLs resets confirmation and COD collection state', async () => {
  order.OrderStatus = 'Shipping'
  const router = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Giao hoàn tất' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(await within(dialog).findByRole('checkbox', { name: /Tôi xác nhận đã giao hàng thành công/ }))
  order = { ...order, OrderId: 'o2', OrderCode: 'DH-API-02' }
  await act(() => router.navigate('/admin/orders/o2'))
  await screen.findByText('Đơn hàng #DH-API-02')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(within(screen.getByRole('banner')).queryByText('/ DH-API-01')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Giao hoàn tất' }))
  const nextDialog = screen.getByRole('dialog')
  expect(await within(nextDialog).findByRole('checkbox', { name: /Tôi xác nhận đã giao hàng thành công/ })).not.toBeChecked()
  expect(api.confirmCodDelivery).not.toHaveBeenCalled()
})
