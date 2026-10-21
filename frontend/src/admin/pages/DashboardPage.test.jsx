import { act, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import useReportingDate from '../hooks/useReportingDate.js'
import DashboardPage from './DashboardPage.jsx'
import AdminNotifications from '../components/AdminNotifications.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), getRevenueSeries: vi.fn(), getDashboardStock: vi.fn(), markNotificationRead: vi.fn(), markAllNotificationsRead: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
const permissions = ['admin.portal', ...['products','orders','inventory','chat','returns','warranties','revenue_reports','order_reports'].map((key) => key + ':view')]
function renderPage(element = <DashboardPage />) {
  return render(<AuthContext.Provider value={makeAuth({ role: 'Admin', permissions })}><MemoryRouter>{element}</MemoryRouter></AuthContext.Provider>)
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.setSystemTime(new Date('2026-10-21T05:00:00Z'))
  api.getAdminData.mockImplementation(async (token, path) => path.includes('/statistics/reports/')
    ? { Summary: { Revenue: '0', Cost: '0', Profit: '0', TotalOrders: 0, DeliveredOrders: 0, CancelledOrders: 0 }, Items: [], Total: 0 }
    : path.endsWith('/workload') ? { PendingOrders: 0, WaitingChats: 0, PendingReturns: 0, NewWarranties: 0 }
    : path.endsWith('/unread-count') ? { Count: 0 } : { Items: [], Total: 0, Page: 1, PageSize: 5 })
  api.getRevenueSeries.mockImplementation(async (token, months) => months.map((month) => ({ month, data: { Revenue: '0', Profit: '0', TotalOrders: 0 }, error: '' })))
  api.getDashboardStock.mockResolvedValue({ Items: [], OutOfStockTotal: 0, LowStockTotal: 0 })
})
afterEach(() => vi.useRealTimers())

describe('dashboard data', () => {
  test('empty APIs show zeros, an empty chart and genuine empty operational tables', async () => {
    renderPage()
    expect(await within(screen.getByRole('article', { name: 'Doanh số bán hàng' })).findByText(/0\s*₫/)).toBeInTheDocument()
    expect(await within(screen.getByRole('article', { name: 'Số đơn đã giao' })).findByText('0')).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Số đơn đã giao' })).getByText('0 / 0')).toBeInTheDocument()
    expect(await within(screen.getByRole('article', { name: 'Số đơn hủy' })).findByText('0')).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Số đơn hủy' })).getByText('0 / 0')).toBeInTheDocument()
    expect(await screen.findByText('Chưa có dữ liệu trong kỳ đã chọn.')).toBeInTheDocument()
    expect(await screen.findByText('Chưa có đơn hàng.')).toBeInTheDocument()
    expect(await screen.findByText('Chưa có sản phẩm cần cảnh báo.')).toBeInTheDocument()
    expect(screen.queryByText(/Doanh thu cao nhất/)).not.toBeInTheDocument()
  })
  test('dashboard uses sales report totals, same elapsed dates, and actionable workload links', async () => {
    api.getAdminData.mockImplementation(async (token, path, query) => {
      if (path.endsWith('/reports/revenue')) return { Summary: { Revenue: query.date_from === '2026-10-01' ? '434000' : '400000', Cost: '300000', Profit: '134000', Margin: '30.88', TotalOrders: 3 } }
      if (path.endsWith('/reports/orders')) return { Summary: { TotalOrders: 10, DeliveredOrders: 4, CancelledOrders: 6 } }
      if (path.endsWith('/workload')) return { PendingOrders: 3, WaitingChats: 2, PendingReturns: 1, NewWarranties: 0 }
      return { Items: [{ OrderId: 'o1', OrderCode: 'VT-real', ReceiverName: 'Người nhận thật', TotalAmount: '524000', OrderStatus: 'Shipping', OrderedAt: '2026-10-12T18:00:00Z' }], Total: 1 }
    })
    api.getRevenueSeries.mockImplementation(async (token, months) => months.map((month, index) => ({ month, data: { Revenue: String((index + 1) * 1000000), Profit: '-10000', TotalOrders: 1 }, error: '' })))
    api.getDashboardStock.mockResolvedValue({ Items: [{ ProductVariantId: 'v1', ProductName: 'Điện thoại thật', VariantName: '256GB', Sku: 'PHONE', StockQuantity: 0 }], OutOfStockTotal: 10, LowStockTotal: 13 })
    renderPage()
    expect(await within(screen.getByRole('article', { name: 'Doanh số bán hàng' })).findByText(/434\.000/)).toBeInTheDocument()
    expect(await within(screen.getByRole('article', { name: 'Số đơn đã giao' })).findByText('4')).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Số đơn đã giao' })).getByText('4 / 10')).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Số đơn hủy' })).getByText('6')).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Số đơn hủy' })).getByText('6 / 10')).toBeInTheDocument()
    expect(screen.queryByRole('article', { name: 'Đơn ghi nhận bán hàng' })).not.toBeInTheDocument()
    expect(screen.queryByRole('article', { name: 'Tỷ lệ hủy' })).not.toBeInTheDocument()
    expect(screen.getByText('+8,5% so với cùng kỳ tháng trước')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Chờ xác nhận' })).toHaveAttribute('href','/admin/orders?status=Pending')
    expect(screen.getByRole('link', { name: 'Chat đang chờ' })).toHaveAttribute('href','/admin/support?tab=waiting')
    expect(screen.getByRole('link', { name: 'Hết hàng' })).toHaveTextContent('Hết hàng: 10')
    expect(screen.getByRole('link', { name: 'Hết hàng' })).toHaveAttribute('href','/admin/products?status=Active&stock=out_of_stock')
    expect(screen.getByRole('link', { name: 'Sắp hết' })).toHaveTextContent('Sắp hết: 13')
    expect(screen.getByRole('link', { name: 'Sắp hết' })).toHaveAttribute('href','/admin/products?status=Active&stock=low_stock')
    expect(screen.getAllByRole('link', { name: /^Xem báo cáo Tháng/ })).toHaveLength(6)
    expect(api.getAdminData).toHaveBeenCalledWith('access-for-test','/admin/statistics/reports/revenue',expect.objectContaining({ date_from:'2026-09-01',date_to:'2026-09-21' }),expect.any(AbortSignal))
    expect(api.getAdminData.mock.calls.some(([,path]) => path === '/admin/statistics/revenue')).toBe(false)
  })
  test('failed inventory stays unknown while other sections render and retry recovers', async () => {
    api.getDashboardStock.mockRejectedValueOnce(new Error('Không kết nối được máy chủ.'))
    renderPage()
    await waitFor(() => expect(screen.getByRole('link', { name: 'Hết hàng' })).toHaveTextContent('Hết hàng: —'))
    expect(await screen.findByText('Chưa có đơn hàng.')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Thử lại' })[0])
    await waitFor(() => expect(screen.getByRole('link', { name: 'Hết hàng' })).toHaveTextContent('Hết hàng: 0'))
    expect(screen.getByRole('link', { name: 'Sắp hết' })).toHaveTextContent('Sắp hết: 0')
  })
  test('leaving cancels every pending request', () => {
    const signals = []
    api.getAdminData.mockImplementation((token,path,query,signal) => { signals.push(signal); return new Promise(() => {}) })
    api.getRevenueSeries.mockImplementation((token,months,signal) => { signals.push(signal); return new Promise(() => {}) })
    api.getDashboardStock.mockImplementation((token,signal) => { signals.push(signal); return new Promise(() => {}) })
    const view = renderPage(); view.unmount()
    expect(signals.length).toBeGreaterThan(0)
    expect(signals.every((signal) => signal.aborted)).toBe(true)
  })
  test('reporting day advances at Vietnam midnight even within the same month', async () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-21T16:59:50Z'))
    const { result, unmount } = renderHook(useReportingDate)
    expect(result.current).toBe('2026-10-21')
    await act(() => vi.advanceTimersByTimeAsync(30000))
    expect(result.current).toBe('2026-10-22')
    unmount()
  })
})
describe('notification menu', () => {
  test('real notifications can be marked read; Escape closes the menu and restores focus', async () => {
    let read = false
    api.getAdminData.mockImplementation(async (token, path) => path.endsWith('/unread-count') ? { Count: read ? 0 : 1 } : { Items: [{ NotificationId: 'n1', Title: 'Đơn cần xử lý', Content: 'Bạn có đơn mới', IsRead: read, CreatedAt: '2026-10-13T07:00:00Z', ActionUrl: 'https://example.com' }], Total: 1 })
    api.markNotificationRead.mockImplementation(async () => { read = true })
    renderPage(<AdminNotifications />)
    expect(await screen.findByText('1 thông báo chưa đọc')).toBeInTheDocument()
    const bell = screen.getByRole('button', { name: 'Thông báo' })
    fireEvent.click(bell)
    expect(await screen.findByText('Đơn cần xử lý')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Xem chi tiết' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Đánh dấu đã đọc' }))
    await waitFor(() => expect(api.markNotificationRead).toHaveBeenCalledWith('access-for-test', 'n1'))
    await waitFor(() => expect(screen.queryByText('1 thông báo chưa đọc')).not.toBeInTheDocument())
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('region', { name: 'Danh sách thông báo' })).not.toBeInTheDocument()
    expect(bell).toHaveFocus()
  })

  test('empty notifications have no red unread dot and show an empty menu', async () => {
    renderPage(<AdminNotifications />)
    fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
    expect(await screen.findByText('Chưa có thông báo.')).toBeInTheDocument()
    expect(screen.queryByText(/thông báo chưa đọc/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Đọc tất cả' })).toBeDisabled()
  })

  test('mark all read refreshes the count and the list from the server', async () => {
    let read = false
    api.getAdminData.mockImplementation(async (token, path) => path.endsWith('/unread-count') ? { Count: read ? 0 : 2 } : { Items: [{ NotificationId: 'n1', Title: 'Thông báo thật', IsRead: read, CreatedAt: '2026-10-13T07:00:00Z' }], Total: 1 })
    api.markAllNotificationsRead.mockImplementation(async () => { read = true; return { Count: 2 } })
    renderPage(<AdminNotifications />)
    await screen.findByText('2 thông báo chưa đọc')
    fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
    await screen.findByText('Thông báo thật')
    fireEvent.click(screen.getByRole('button', { name: 'Đọc tất cả' }))
    await waitFor(() => expect(api.markAllNotificationsRead).toHaveBeenCalledWith('access-for-test'))
    await waitFor(() => expect(screen.queryByText('2 thông báo chưa đọc')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Đọc tất cả' })).toBeDisabled()
  })
})
