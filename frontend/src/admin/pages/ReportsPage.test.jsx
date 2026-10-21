import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
let fail, total, missing, cancelledTotal, cancelledFailure, deliveredTotal, deliveredFailure
const options = { Categories: [{ Id: 'cat1', Name: 'Điện thoại từ API' }], Brands: [{ Id: 'b1', Name: 'Hãng từ API' }], Products: [{ Id: 'p1', Name: 'Sản phẩm từ API', CategoryId: 'cat1', BrandId: 'b1' }] }
beforeEach(() => {
  vi.resetAllMocks(); fail = false; total = 1; missing = false; cancelledTotal = 1; cancelledFailure = false; deliveredTotal = 2; deliveredFailure = false
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/statistics/report-options') return structuredClone(options)
    if (path === '/admin/statistics/reports/orders/delivered') {
      if (deliveredFailure) throw new Error('Không tải được danh sách đơn đã giao')
      const start = (query.page - 1) * query.page_size
      return { Items: Array.from({ length: Math.max(0, Math.min(query.page_size, deliveredTotal - start)) }, (_, index) => {
        const number = start + index + 1
        return { OrderId: 'delivered-' + number, OrderCode: 'VT-GIAO-' + number, OrderedAt: '2026-09-15T01:00:00Z', DeliveredAt: number === 1 ? '2026-10-01T17:00:00Z' : null, CustomerName: 'Khách ' + number, TotalAmount: '130000', OrderStatus: number === 1 ? 'Delivered' : 'Completed' }
      }), Total: deliveredTotal, Page: query.page, PageSize: query.page_size }
    }
    if (path === '/admin/statistics/reports/orders/cancelled') {
      if (cancelledFailure) throw new Error('Không tải được danh sách đơn hủy')
      const start = (query.page - 1) * query.page_size
      return { Items: Array.from({ length: Math.max(0, Math.min(query.page_size, cancelledTotal - start)) }, (_, index) => {
        const number = start + index + 1
        return { OrderId: 'cancelled-' + number, OrderCode: 'VT-HUY-' + number, OrderedAt: '2026-09-15T01:00:00Z', CustomerName: 'Khách ' + number, TotalAmount: '130000', CancelReason: number === 1 ? 'Đổi nhu cầu mua hàng' : '   ' }
      }), Total: cancelledTotal, Page: query.page, PageSize: query.page_size }
    }
    if (path === '/admin/statistics/reports/revenue/lines') return { Items: [{ Key: 'line', OrderId: 'o1', OrderCode: 'VT-001', DeliveredAt: '2026-10-01T17:00:00Z', Sku: 'SKU-1', VariantInfo: '128GB', Quantity: 1, UnitPrice: '110000', Discount: '10000', UnitCost: '60000', Revenue: '100000', Cost: '60000', Profit: '40000' }], Total: 1 }
    if (path.startsWith('/admin/statistics/reports/')) {
      if (fail) throw new Error('Lỗi đọc báo cáo')
      const orders = path.endsWith('/orders')
      const product = { Key: 'row' + query.page, ProductId: 'p1', ProductName: 'Doanh số trang ' + query.page, CategoryName: 'Điện thoại', BrandName: 'Hãng', Quantity: 1, Revenue: '100000', Cost: missing ? null : '60000', Profit: missing ? null : '40000', Margin: missing ? null : '40', LinesMissingCost: missing ? 1 : 0 }
      return { Period: { DateFrom: query.date_from, DateTo: query.date_to },
        Summary: { Revenue: '100000', Cost: missing ? null : '60000', Profit: missing ? null : '40000', Margin: missing ? null : '40', LinesMissingCost: missing ? 1 : 0, TotalOrders: orders ? cancelledTotal + deliveredTotal + 1 : 4, DeliveredOrders: deliveredTotal, InProgressOrders: 1, CancelledOrders: cancelledTotal, Quantity: 1, AverageOrderValue: '25000' },
        Chart: [{ DateFrom: query.date_from, Label: '01/10', Revenue: '60000', Profit: '20000', TotalOrders: 2, DeliveredOrders: 1, InProgressOrders: 1, CancelledOrders: 0 }, { DateFrom: '2026-10-02', Label: '02/10', Revenue: '40000', Profit: '20000', TotalOrders: 2, DeliveredOrders: 1, InProgressOrders: 0, CancelledOrders: 1 }],
        Items: total ? [orders ? { Key: 'month', DateFrom: query.date_from, TotalOrders: 4, DeliveredOrders: 2, InProgressOrders: 1, CancelledOrders: 1 } : product] : [],
        TopProducts: [], Total: total, CancellationReasons: [] }
    }
    return { Items: [], Total: 0 }
  })
})
function open(path = '/admin/reports', role = 'Admin', permissions = ['admin.portal','profile:read','revenue_reports:view','order_reports:view','orders:view']) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
test('summary and product table keep daily chart points from the report API', async () => {
  open('/admin/reports?period=month&month=2026-09')
  await screen.findByText('Doanh số trang 1')
  expect(within(screen.getByRole('article', { name: 'Doanh số bán hàng' })).getByText(/100\.000/)).toBeInTheDocument()
  expect(screen.getByRole('img').querySelectorAll('rect')).toHaveLength(2)
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/revenue',
    expect.objectContaining({ date_from: '2026-09-01', date_to: '2026-09-30', sort: 'revenue_desc' }), expect.any(AbortSignal))
})
test('filters persist in URL, survive switching tabs and restore with Back', async () => {
  const router = open()
  await screen.findByText('Doanh số trang 1')
  fireEvent.change(screen.getByRole('combobox', { name: 'Danh mục', exact: true }), { target: { value: 'cat1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  await waitFor(() => expect(router.state.location.search).toContain('category_id=cat1'))
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Loại báo cáo' })).getByRole('button', { name: 'Đơn hàng', exact: true }))
  await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/orders', expect.objectContaining({ category_id: 'cat1' }), expect.any(AbortSignal)))
  await screen.findByText('Tỷ lệ hủy 25%')
  expect(screen.getByRole('combobox', { name: 'Danh mục', exact: true })).toHaveValue('cat1')
  await act(() => router.navigate(-1))
  await screen.findByText('Doanh số trang 1')
  expect(screen.getByRole('combobox', { name: 'Danh mục', exact: true })).toHaveValue('cat1')
})
test('pagination and server sorting preserve filters and reset to the first page', async () => {
  total = 11; const router = open('/admin/reports?period=month&month=2025-12')
  await screen.findByText('Doanh số trang 1')
  fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
  await screen.findByText('Doanh số trang 2')
  fireEvent.change(screen.getByRole('combobox', { name: 'Sắp xếp sản phẩm' }), { target: { value: 'profit_asc' } })
  await screen.findByText('Doanh số trang 1')
  expect(router.state.location.search).toContain('month=2025-12')
  expect(api.getAdminData).toHaveBeenLastCalledWith('access-for-test', '/admin/statistics/reports/revenue', expect.objectContaining({ page: 1, sort: 'profit_asc' }), expect.any(AbortSignal))
})
test('product drilldown uses the applied period and opens an actual order link', async () => {
  const router = open('/admin/reports?period=month&month=2026-09&brand_id=b1')
  await screen.findByText('Doanh số trang 1')
  fireEvent.click(screen.getByRole('button', { name: 'Doanh số trang 1' }))
  const dialog = await screen.findByRole('dialog')
  expect(await within(dialog).findByRole('link', { name: 'VT-001' })).toHaveAttribute('href','/admin/orders/o1')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test','/admin/statistics/reports/revenue/lines',expect.objectContaining({ product_id: 'p1', brand_id: 'b1', date_from: '2026-09-01', date_to: '2026-09-30' }),expect.any(AbortSignal))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Đóng' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(router.state.location.search).toContain('brand_id=b1')
})

test('opening an order and using its back button restores filters, page, sorting and the product drawer', async () => {
  const read = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation(async (token, path, query, signal) => {
    if (path === '/admin/orders/o1') return { OrderId: 'o1', OrderCode: 'VT-001', OrderStatus: 'Completed', PaymentStatus: 'Paid', ReceiverName: 'Người nhận', Items: [], StatusHistories: [] }
    return read(token, path, query, signal)
  })
  total = 11
  const router = open('/admin/reports?period=month&month=2026-09&brand_id=b1&sort=profit_asc&page=2')
  await screen.findByText('Doanh số trang 2')
  fireEvent.click(screen.getByRole('button', { name: 'Doanh số trang 2' }))
  const dialog = await screen.findByRole('dialog')
  const origin = router.state.location.search
  fireEvent.click(await within(dialog).findByRole('link', { name: 'VT-001' }))
  fireEvent.click(await screen.findByRole('button', { name: '← Quay lại báo cáo' }))
  await screen.findByRole('dialog')
  expect(router.state.location.pathname).toBe('/admin/reports')
  expect(router.state.location.search).toBe(origin)
  expect(screen.getByRole('combobox', { name: 'Sắp xếp sản phẩm' })).toHaveValue('profit_asc')
})
test('refresh clamps stale pages and API errors can recover without false zero revenue', async () => {
  total = 11; open()
  await screen.findByText('Doanh số trang 1')
  fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
  await screen.findByText('Doanh số trang 2')
  total = 1
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByText('Doanh số trang 1')
  fail = true
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await waitFor(() => expect(within(screen.getByRole('article', { name: 'Doanh số bán hàng' })).getByText('—')).toBeInTheDocument())
  fail = false
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByText('Doanh số trang 1')
})
test('Staff can read snapshots and missing import prices stay unknown', async () => {
  missing = true; open('/admin/reports','Staff')
  await screen.findByText('Doanh số trang 1')
  expect(within(screen.getByRole('article', { name: 'Lãi gộp' })).getByText('Chưa đủ dữ liệu')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Xuất báo cáo' })).not.toBeInTheDocument()
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/users'))).toBe(false)
})
test('revisiting reports through the sidebar clears the filters', async () => {
  open('/admin/reports?category_id=cat1')
  await screen.findByText('Doanh số trang 1')
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Báo cáo thống kê' }))
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Danh mục', exact: true })).toHaveValue(''))
})

test.each(['Admin', 'Staff'])('%s opens cancelled orders on demand with the same period and catalog filters', async (role) => {
  cancelledTotal = 2
  const router = open('/admin/reports?tab=orders&period=month&month=2026-09&category_id=cat1&brand_id=b1&product_id=p1', role)
  const trigger = await screen.findByRole('button', { name: 'Xem danh sách đơn đã hủy' })
  await waitFor(() => expect(trigger).toBeEnabled())
  expect(api.getAdminData.mock.calls.some(([, path]) => path.endsWith('/orders/cancelled'))).toBe(false)
  fireEvent.click(trigger)
  const details = await screen.findByRole('region', { name: 'Đơn đã hủy trong kỳ' })
  expect(await within(details).findByRole('link', { name: 'VT-HUY-1' })).toHaveAttribute('href', '/admin/orders/cancelled-1')
  expect(within(details).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Mã đơn', 'Ngày đặt', 'Khách hàng', 'Giá trị đơn', 'Lý do hủy'])
  expect(within(details).getByText('Khách 1')).toBeInTheDocument()
  expect(within(details).getByText('Đổi nhu cầu mua hàng')).toBeInTheDocument()
  expect(within(details).getByText('Không ghi lý do')).toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/orders/cancelled', {
    date_from: '2026-09-01', date_to: '2026-09-30', category_id: 'cat1', brand_id: 'b1', product_id: 'p1', page: 1, page_size: 10,
  }, expect.any(AbortSignal))
  fireEvent.click(within(details).getByRole('button', { name: 'Đóng danh sách' }))
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Đơn đã hủy trong kỳ' })).not.toBeInTheDocument())
  expect(router.state.location.search).toContain('product_id=p1')
  expect(router.state.location.search).not.toContain('cancelled=')
  expect(screen.getByRole('button', { name: 'Xem danh sách đơn đã hủy' })).toHaveFocus()
})

test('cancelled order pagination, refresh, filters and tab history keep the detail context', async () => {
  cancelledTotal = 11
  const router = open('/admin/reports?tab=orders&period=month&month=2026-09&brand_id=b1&cancelled=1&cancelled_page=2')
  await screen.findByRole('link', { name: 'VT-HUY-11' })
  cancelledTotal = 1
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByRole('link', { name: 'VT-HUY-1' })
  await waitFor(() => expect(router.state.location.search).toContain('cancelled_page=1'))
  cancelledTotal = 11
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  const pagination = await screen.findByRole('navigation', { name: 'Phân trang đơn đã hủy' })
  fireEvent.click(within(pagination).getByRole('button', { name: 'Trang sau' }))
  await screen.findByRole('link', { name: 'VT-HUY-11' })
  fireEvent.change(screen.getByLabelText('Tháng', { exact: true }), { target: { value: '2025-12' } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  await screen.findByRole('link', { name: 'VT-HUY-1' })
  expect(router.state.location.search).toContain('cancelled=1')
  expect(router.state.location.search).not.toContain('cancelled_page=')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/orders/cancelled', expect.objectContaining({ date_from: '2025-12-01', date_to: '2025-12-31', brand_id: 'b1', page: 1 }), expect.any(AbortSignal))
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Loại báo cáo' })).getByRole('button', { name: 'Bán hàng & lãi gộp' }))
  await screen.findByText('Doanh số trang 1')
  expect(screen.queryByRole('region', { name: 'Đơn đã hủy trong kỳ' })).not.toBeInTheDocument()
  await act(() => router.navigate(-1))
  await screen.findByRole('link', { name: 'VT-HUY-1' })
  expect(router.state.location.search).toContain('month=2025-12')
})

test('return from a cancelled order restores the report detail page and filters', async () => {
  cancelledTotal = 11
  const read = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation(async (token, path, query, signal) => path === '/admin/orders/cancelled-11'
    ? { OrderId: 'cancelled-11', OrderCode: 'VT-HUY-11', OrderStatus: 'Cancelled', PaymentStatus: 'Pending', ReceiverName: 'Người nhận', Items: [], StatusHistories: [] }
    : read(token, path, query, signal))
  const router = open('/admin/reports?tab=orders&period=month&month=2026-09&brand_id=b1&cancelled=1&cancelled_page=2')
  const link = await screen.findByRole('link', { name: 'VT-HUY-11' })
  const origin = router.state.location.search
  fireEvent.click(link)
  fireEvent.click(await screen.findByRole('button', { name: '← Quay lại báo cáo' }))
  await screen.findByRole('link', { name: 'VT-HUY-11' })
  expect(router.state.location.search).toBe(origin)
})

test('cancelled detail empty and failed reads stay explicit and retry refreshes the summary too', async () => {
  cancelledTotal = 0
  open('/admin/reports?tab=orders&period=month&month=2026-09&cancelled=1')
  const details = await screen.findByRole('region', { name: 'Đơn đã hủy trong kỳ' })
  await within(details).findByText('Không có đơn đã hủy trong kỳ theo bộ lọc đang chọn.')
  cancelledFailure = true
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await within(details).findByText('Không tải được danh sách đơn hủy')
  cancelledFailure = false; cancelledTotal = 1
  fireEvent.click(within(details).getByRole('button', { name: 'Thử lại' }))
  await within(details).findByRole('link', { name: 'VT-HUY-1' })
  expect(within(screen.getByRole('article', { name: 'Đã hủy', exact: true })).getByText('1')).toBeInTheDocument()
})

test('report readers without order view permission see order codes without inaccessible links', async () => {
  open('/admin/reports?tab=orders&cancelled=1', 'Staff', ['admin.portal', 'revenue_reports:view', 'order_reports:view'])
  const details = await screen.findByRole('region', { name: 'Đơn đã hủy trong kỳ' })
  await within(details).findByText('VT-HUY-1')
  expect(within(details).queryByRole('link')).not.toBeInTheDocument()
})

test.each(['Admin', 'Staff'])('%s opens delivered orders with the applied filters and Vietnamese statuses', async (role) => {
  const router = open('/admin/reports?tab=orders&period=month&month=2026-09&category_id=cat1&brand_id=b1&product_id=p1', role)
  const trigger = await screen.findByRole('button', { name: 'Xem danh sách đơn đã giao' })
  await waitFor(() => expect(trigger).toBeEnabled())
  expect(api.getAdminData.mock.calls.some(([, path]) => path.endsWith('/orders/delivered'))).toBe(false)
  fireEvent.click(trigger)
  const details = await screen.findByRole('region', { name: 'Đơn đã giao trong kỳ' })
  expect(await within(details).findByRole('link', { name: 'VT-GIAO-1' })).toHaveAttribute('href', '/admin/orders/delivered-1')
  expect(within(details).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Mã đơn', 'Ngày đặt', 'Ngày giao', 'Khách hàng', 'Giá trị đơn', 'Trạng thái'])
  expect(within(details).getByText('Đã giao', { exact: true })).toBeInTheDocument()
  expect(within(details).getByText('Hoàn tất', { exact: true })).toBeInTheDocument()
  expect(within(details).getByText('00:00 02/10/2026')).toBeInTheDocument()
  expect(within(details).getByText('—', { exact: true })).toBeInTheDocument()
  expect(within(details).getByText(/kể cả khi chưa thanh toán/)).toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/orders/delivered', {
    date_from: '2026-09-01', date_to: '2026-09-30', category_id: 'cat1', brand_id: 'b1', product_id: 'p1', page: 1, page_size: 10,
  }, expect.any(AbortSignal))
  fireEvent.click(within(details).getByRole('button', { name: 'Đóng danh sách' }))
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Đơn đã giao trong kỳ' })).not.toBeInTheDocument())
  expect(router.state.location.search).toContain('product_id=p1')
  expect(router.state.location.search).not.toContain('delivered=')
  expect(screen.getByRole('button', { name: 'Xem danh sách đơn đã giao' })).toHaveFocus()
})

test('delivered pagination and filters reset correctly and switching lists preserves browser history', async () => {
  deliveredTotal = 11
  const router = open('/admin/reports?tab=orders&period=month&month=2026-09&brand_id=b1&delivered=1&delivered_page=2')
  await screen.findByRole('link', { name: 'VT-GIAO-11' })
  deliveredTotal = 1
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByRole('link', { name: 'VT-GIAO-1' })
  await waitFor(() => expect(router.state.location.search).toContain('delivered_page=1'))
  deliveredTotal = 11
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  const pagination = await screen.findByRole('navigation', { name: 'Phân trang đơn đã giao' })
  fireEvent.click(within(pagination).getByRole('button', { name: 'Trang sau' }))
  await screen.findByRole('link', { name: 'VT-GIAO-11' })
  fireEvent.change(screen.getByLabelText('Tháng', { exact: true }), { target: { value: '2025-12' } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  await screen.findByRole('link', { name: 'VT-GIAO-1' })
  expect(router.state.location.search).toContain('delivered=1')
  expect(router.state.location.search).not.toContain('delivered_page=')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/orders/delivered', expect.objectContaining({ date_from: '2025-12-01', date_to: '2025-12-31', brand_id: 'b1', page: 1 }), expect.any(AbortSignal))
  fireEvent.click(screen.getByRole('button', { name: 'Xem danh sách đơn đã hủy' }))
  await screen.findByRole('link', { name: 'VT-HUY-1' })
  expect(screen.queryByRole('region', { name: 'Đơn đã giao trong kỳ' })).not.toBeInTheDocument()
  expect(router.state.location.search).not.toContain('delivered=')
  await act(() => router.navigate(-1))
  await screen.findByRole('link', { name: 'VT-GIAO-1' })
  expect(screen.queryByRole('region', { name: 'Đơn đã hủy trong kỳ' })).not.toBeInTheDocument()
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Loại báo cáo' })).getByRole('button', { name: 'Bán hàng & lãi gộp' }))
  await screen.findByText('Doanh số trang 1')
  expect(router.state.location.search).not.toContain('delivered=')
})

test('returning from a delivered order restores the exact report URL and detail page', async () => {
  deliveredTotal = 11
  const read = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation(async (token, path, query, signal) => path === '/admin/orders/delivered-11'
    ? { OrderId: 'delivered-11', OrderCode: 'VT-GIAO-11', OrderStatus: 'Completed', PaymentStatus: 'Pending', ReceiverName: 'Người nhận', Items: [], StatusHistories: [] }
    : read(token, path, query, signal))
  const router = open('/admin/reports?tab=orders&period=month&month=2026-09&brand_id=b1&delivered=1&delivered_page=2')
  const link = await screen.findByRole('link', { name: 'VT-GIAO-11' })
  const origin = router.state.location.search
  fireEvent.click(link)
  fireEvent.click(await screen.findByRole('button', { name: '← Quay lại báo cáo' }))
  await screen.findByRole('link', { name: 'VT-GIAO-11' })
  expect(router.state.location.search).toBe(origin)
})

test('delivered empty and failed reads recover with a consistent summary', async () => {
  deliveredTotal = 0
  open('/admin/reports?tab=orders&delivered=1')
  const details = await screen.findByRole('region', { name: 'Đơn đã giao trong kỳ' })
  await within(details).findByText('Không có đơn đã giao trong kỳ theo bộ lọc đang chọn.')
  deliveredFailure = true
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await within(details).findByText('Không tải được danh sách đơn đã giao')
  deliveredFailure = false; deliveredTotal = 2
  fireEvent.click(within(details).getByRole('button', { name: 'Thử lại' }))
  await within(details).findByRole('link', { name: 'VT-GIAO-1' })
  expect(within(screen.getByRole('article', { name: 'Đã giao', exact: true })).getByText('2')).toBeInTheDocument()
})

test('delivered order codes remain readable without order-view permission', async () => {
  open('/admin/reports?tab=orders&delivered=1', 'Staff', ['admin.portal', 'revenue_reports:view', 'order_reports:view'])
  const details = await screen.findByRole('region', { name: 'Đơn đã giao trong kỳ' })
  await within(details).findByText('VT-GIAO-1')
  expect(within(details).queryByRole('link')).not.toBeInTheDocument()
})
