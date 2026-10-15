import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'
import { monthLabel, monthPeriod, recentMonths } from '../../lib/dashboard-periods.js'

const api = vi.hoisted(() => ({ getAdminData: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
let fail, total
const options = { Categories: [{ Id: 'cat1', Name: 'Điện thoại từ API' }], Brands: [{ Id: 'b1', Name: 'Hãng từ API' }], Products: [{ Id: 'p1', Name: 'Sản phẩm từ API', CategoryId: 'cat1', BrandId: 'b1' }] }
const period = { DateFrom: '2026-10-01', DateTo: '2026-10-31' }
beforeEach(() => {
  vi.resetAllMocks(); fail = false; total = 1
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/statistics/report-options') return structuredClone(options)
    if (path.startsWith('/admin/statistics/reports/')) {
      if (fail) throw new Error('Lỗi đọc báo cáo')
      const orders = path.endsWith('/orders')
      return { Period: period, Summary: { Revenue: '100000.00', TotalOrders: 4, DeliveredOrders: 2, CancelledOrders: 1, AverageOrderValue: '25000', PeakRevenue: '100000' }, Chart: [{ DateFrom: '2026-10-01', DateTo: '2026-10-07', Label: '01–07/10', Revenue: '100000', TotalOrders: 4, DeliveredOrders: 2, CancelledOrders: 1 }], Items: total ? [{ Key: 'row' + query.page, DateFrom: '2026-10-01', DateTo: '2026-10-07', ...(orders ? { TotalOrders: 4, DeliveredOrders: 2, CancelledOrders: 1 } : { ProductName: 'Doanh số trang ' + query.page, CategoryName: 'Điện thoại', BrandName: 'Hãng', Revenue: '100000.00' }) }] : [], Total: total }
    }
    throw new Error('Unexpected API path: ' + path)
  })
})

function open(path = '/admin/reports', role = 'Admin', grants = ['revenue_reports:view', 'order_reports:view']) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: ['admin.portal', ...grants] })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

test('real route loads revenue by default, uses API values and excludes removed controls', async () => {
  open()
  await screen.findByText('Doanh số trang 1', {}, { timeout: 5000 })
  expect(screen.getByRole('heading', { level: 1, name: 'Báo cáo thống kê' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thống kê theo doanh thu', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(screen.queryByRole('button', { name: 'Xuất báo cáo' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('combobox').map((select) => select.closest('label').firstChild.textContent)).toEqual(['Thời gian', 'Danh mục', 'Thương hiệu', 'Sản phẩm'])
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/revenue', expect.objectContaining({ page: 1, page_size: 10 }), expect.any(AbortSignal))
  expect(within(screen.getByRole('region', { name: 'Tổng doanh thu', exact: true })).getByText(/100\.000/)).toBeInTheDocument()
  expect(within(screen.getByRole('table')).getByText('Tháng 10/2026')).toBeInTheDocument()
  expect(within(screen.getByRole('table')).queryByText(/01\/10\/2026.*07\/10\/2026/)).not.toBeInTheDocument()
})

test('applied filters are sent to both report types and survive tab navigation', async () => {
  const router = open()
  await screen.findByText('Doanh số trang 1', {}, { timeout: 5000 })
  await screen.findByRole('option', { name: 'Điện thoại từ API' })
  api.getAdminData.mockClear()
  fireEvent.change(screen.getByRole('combobox', { name: 'Danh mục', exact: true }), { target: { value: 'cat1' } })
  expect(api.getAdminData).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/revenue', expect.objectContaining({ category_id: 'cat1', page: 1 }), expect.any(AbortSignal)))
  fireEvent.click(screen.getByRole('button', { name: 'Thống kê theo số lượng đơn hàng', exact: true }))
  await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/orders', expect.objectContaining({ category_id: 'cat1' }), expect.any(AbortSignal)))
  expect(router.state.location.search).toBe('?tab=orders')
  await waitFor(() => expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Thời gian', 'Tổng đơn', 'Giao thành công', 'Đã hủy', 'Tỷ lệ hủy']))
  await screen.findByText('25%')
})

test('pagination uses server total and filters reset to first page', async () => {
  total = 11; open()
  await screen.findByText('Doanh số trang 1', {}, { timeout: 5000 })
  fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
  await screen.findByText('Doanh số trang 2')
  expect(screen.getByRole('button', { name: 'Trang 2', exact: true })).toHaveAttribute('aria-current', 'page')
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  await screen.findByText('Doanh số trang 1')
})

test.each(['revenue', 'orders'])('time and catalog filters update monthly table in %s report', async (tab) => {
  const read = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation(async (token, path, query, signal) => {
    const data = await read(token, path, query, signal)
    if (!path.startsWith('/admin/statistics/reports/')) return data
    return { ...data, Items: data.Items.map((row) => ({ ...row, DateFrom: query.date_from, DateTo: query.date_to })) }
  })
  open('/admin/reports?tab=' + tab)
  await screen.findByRole('table', {}, { timeout: 5000 })
  await screen.findByRole('option', { name: 'Sản phẩm từ API' })
  const targetMonth = `${new Date().getFullYear()}-12`
  fireEvent.change(screen.getByRole('combobox', { name: 'Thời gian', exact: true }), { target: { value: targetMonth } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Danh mục', exact: true }), { target: { value: 'cat1' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Thương hiệu', exact: true }), { target: { value: 'b1' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Sản phẩm', exact: true }), { target: { value: 'p1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  await waitFor(() => expect(within(screen.getByRole('table')).getByText(monthLabel(targetMonth))).toBeInTheDocument())
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/' + tab,
    { ...monthPeriod(targetMonth), category_id: 'cat1', brand_id: 'b1', product_id: 'p1', page: 1, page_size: 10 }, expect.any(AbortSignal))
})

test('Staff can open order tab directly without account lookup or export permission', async () => {
  open('/admin/reports?tab=orders', 'Staff')
  await screen.findByText('25%', {}, { timeout: 5000 })
  expect(screen.getByRole('button', { name: 'Thống kê theo số lượng đơn hàng', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(api.getAdminData.mock.calls.some(([, path]) => path.startsWith('/admin/users'))).toBe(false)
  expect(screen.queryByRole('button', { name: 'Xuất báo cáo' })).not.toBeInTheDocument()
})

test.each(['revenue', 'orders'])('%s uses one monthly bar or five bars and preserves selection between tabs', async (tab) => {
  const read = api.getAdminData.getMockImplementation()
  api.getAdminData.mockImplementation(async (token, path, query, signal) => {
    const data = await read(token, path, query, signal)
    if (!path.startsWith('/admin/statistics/reports/')) return data
    const first = query.date_from.slice(0, 7), last = query.date_to.slice(0, 7)
    const count = (Number(last.slice(0, 4)) - Number(first.slice(0, 4))) * 12 + Number(last.slice(5)) - Number(first.slice(5)) + 1
    const months = recentMonths(last, count)
    return { ...data, Period: { DateFrom: query.date_from, DateTo: query.date_to },
      Summary: { ...data.Summary, Revenue: String(count * 100000), TotalOrders: count * 4 },
      Chart: months.map((month) => ({ DateFrom: month + '-01', Label: monthLabel(month), Revenue: '100000', TotalOrders: 4, DeliveredOrders: 2, CancelledOrders: 1 })),
      Items: months.map((month) => ({ ...data.Items[0], Key: month, DateFrom: month + '-01', DateTo: monthPeriod(month).date_to })), Total: count }
  })
  open('/admin/reports?tab=' + tab)
  const title = () => tab === 'revenue' ? 'Doanh thu theo thời gian' : 'Số lượng đơn hàng theo thời gian'
  await waitFor(() => expect(screen.getByRole('img', { name: title() }).querySelectorAll('rect')).toHaveLength(1), { timeout: 5000 })
  const january = `${new Date().getFullYear()}-01`
  fireEvent.change(screen.getByRole('combobox', { name: 'Thời gian', exact: true }), { target: { value: january } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  await waitFor(() => expect(within(screen.getByRole('img', { name: title() })).getByText(monthLabel(january))).toBeInTheDocument())
  expect(screen.getByRole('img', { name: title() }).querySelectorAll('rect')).toHaveLength(1)
  fireEvent.change(screen.getByRole('combobox', { name: 'Thời gian', exact: true }), { target: { value: 'recent' } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  await waitFor(() => expect(screen.getByRole('img', { name: title() }).querySelectorAll('rect')).toHaveLength(5))
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(6)
  fireEvent.click(screen.getByRole('button', { name: tab === 'revenue' ? 'Thống kê theo số lượng đơn hàng' : 'Thống kê theo doanh thu', exact: true }))
  await waitFor(() => expect(screen.getByRole('img').querySelectorAll('rect')).toHaveLength(5))
  expect(screen.getByRole('combobox', { name: 'Thời gian', exact: true })).toHaveValue('recent')
})

test('refresh moves back to an existing page if the report has fewer rows', async () => {
  total = 11; open()
  await screen.findByText('Doanh số trang 1', {}, { timeout: 5000 })
  fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
  await screen.findByText('Doanh số trang 2')
  total = 1
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByText('Doanh số trang 1')
  expect(screen.queryByRole('button', { name: 'Trang sau' })).not.toBeInTheDocument()
})

test('report errors retry from live endpoint; sidebar revisiting resets applied filters', async () => {
  fail = true; open()
  await screen.findByText('Lỗi đọc báo cáo', {}, { timeout: 5000 })
  fail = false
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByText('Doanh số trang 1')
  fireEvent.change(screen.getByRole('combobox', { name: 'Danh mục', exact: true }), { target: { value: 'cat1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Áp dụng' }))
  await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/statistics/reports/revenue', expect.objectContaining({ category_id: 'cat1' }), expect.any(AbortSignal)))
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Báo cáo thống kê' }))
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Danh mục', exact: true })).toHaveValue(''))
})
