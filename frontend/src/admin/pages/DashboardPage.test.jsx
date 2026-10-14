import { act, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { browserMonth } from '../../lib/dashboard-periods.js'
import useBrowserMonth from '../hooks/useBrowserMonth.js'
import DashboardPage from './DashboardPage.jsx'
import AdminNotifications from '../components/AdminNotifications.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), getRevenueSeries: vi.fn(), getDashboardStock: vi.fn(), markNotificationRead: vi.fn(), markAllNotificationsRead: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)

function renderPage(element = <DashboardPage />) {
  return render(<AuthContext.Provider value={makeAuth({ role: 'Admin' })}><MemoryRouter>{element}</MemoryRouter></AuthContext.Provider>)
}

beforeEach(() => {
  vi.resetAllMocks()
  api.getAdminData.mockImplementation(async (token, path) => path.endsWith('/statistics/orders')
    ? { TotalOrders: 0, ByStatus: { Pending: 0 } }
    : path.endsWith('/unread-count') ? { Count: 0 } : { Items: [], Total: 0, Page: 1, PageSize: 5 })
  api.getRevenueSeries.mockImplementation(async (token, months) => months.map((month) => ({ month, data: { NetRevenue: '0.00', OrderCount: 0 }, error: '' })))
  api.getDashboardStock.mockResolvedValue({ Items: [], Total: 0 })
})
afterEach(() => vi.useRealTimers())

describe('dashboard data', () => {
  test('empty APIs show zero cards, table columns and no made-up bars or rows', async () => {
    renderPage()
    for (const name of ['Tổng đơn hàng', 'Đơn chờ xử lý', 'Sản phẩm sắp hết']) expect(await within(screen.getByRole('article', { name })).findByText('0')).toBeInTheDocument()
    expect(await within(screen.getByRole('article', { name: 'Doanh thu' })).findByText(/0\s*₫/)).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: 'Chưa có dữ liệu doanh thu trong 5 tháng gần nhất' })).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /^Tháng/ })).not.toBeInTheDocument()
    const orders = screen.getByRole('region', { name: 'Đơn hàng mới nhất' })
    for (const name of ['Mã đơn', 'Người nhận', 'Giá trị', 'Trạng thái', 'Ngày đặt']) expect(within(orders).getByRole('columnheader', { name })).toBeInTheDocument()
    expect(await screen.findByText('Chưa có đơn hàng.')).toBeInTheDocument()
    expect(await screen.findByText('Chưa có sản phẩm cần cảnh báo.')).toBeInTheDocument()
    expect(screen.queryByText(/so với tháng trước/)).not.toBeInTheDocument()
  })

  test('real data fills the cards, status rows, five bars and the full low-stock count', async () => {
    api.getAdminData.mockImplementation(async (token, path, query) => path.endsWith('/statistics/orders')
      ? { TotalOrders: query.date_from.startsWith(browserMonth()) ? 12 : 10 }
      : path === '/admin/orders' && query.order_status ? { Items: [], Total: 3 }
        : { Items: [{ OrderId: 'o1', OrderCode: 'VT-real', ReceiverName: 'Người nhận thật', TotalAmount: '1200000.00', OrderStatus: 'Shipping', OrderedAt: '2026-10-12T18:00:00Z' }], Total: 1 })
    api.getRevenueSeries.mockImplementation(async (token, months) => months.map((month, index) => ({ month, data: { NetRevenue: String((index + 1) * 1000000), OrderCount: 1 }, error: '' })))
    api.getDashboardStock.mockResolvedValue({ Items: [{ ProductVariantId: 'v1', ProductName: 'Điện thoại thật', VariantName: '256GB', Sku: 'PHONE', StockQuantity: 0 }], Total: 23 })
    renderPage()
    expect(await within(screen.getByRole('article', { name: 'Sản phẩm sắp hết' })).findByText('23')).toBeInTheDocument()
    expect(await screen.findByText('VT-real')).toBeInTheDocument()
    expect(screen.getByText('Đang giao')).toBeInTheDocument()
    expect(screen.getByText('Người nhận thật')).toBeInTheDocument()
    expect(screen.getByText('Điện thoại thật')).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: /^Tháng/ })).toHaveLength(5)
    expect(screen.getByText('+20% so với tháng trước')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Xem tất cả (23)' })).toHaveAttribute('href', '/admin/inventory?tab=low-stock')
  })

  test('failed APIs stay errors while other sections render; retry recovers', async () => {
    api.getDashboardStock.mockRejectedValueOnce(new Error('Không kết nối được máy chủ.'))
    renderPage()
    expect(await within(screen.getByRole('article', { name: 'Sản phẩm sắp hết' })).findByText('—')).toBeInTheDocument()
    expect(await screen.findByText('Chưa có đơn hàng.')).toBeInTheDocument()
    api.getDashboardStock.mockResolvedValue({ Items: [], Total: 0 })
    fireEvent.click(screen.getAllByRole('button', { name: 'Thử lại' })[0])
    expect(await within(screen.getByRole('article', { name: 'Sản phẩm sắp hết' })).findByText('0')).toBeInTheDocument()
  })

  test('leaving the page cancels the requests, including revenue series', () => {
    const signals = []
    api.getAdminData.mockImplementation((token, path, query, signal) => { signals.push(signal); return new Promise(() => {}) })
    api.getRevenueSeries.mockImplementation((token, months, signal) => { signals.push(signal); return new Promise(() => {}) })
    api.getDashboardStock.mockImplementation((token, signal) => { signals.push(signal); return new Promise(() => {}) })
    const view = renderPage()
    view.unmount()
    expect(signals.length).toBeGreaterThan(0)
    expect(signals.every((signal) => signal.aborted)).toBe(true)
  })

  test('the computer clock advances the current month without reloading', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 11, 31, 23, 59, 50))
    const { result, unmount } = renderHook(useBrowserMonth)
    expect(result.current).toBe('2026-12')
    await act(() => vi.advanceTimersByTimeAsync(30000))
    expect(result.current).toBe('2027-01')
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
