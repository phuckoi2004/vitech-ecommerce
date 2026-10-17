import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'
import AdminNotifications from './AdminNotifications.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), markNotificationRead: vi.fn(), markAllNotificationsRead: vi.fn() }))
vi.mock('../../services/api/admin.js', () => ({ ...api, getDashboardStock: async () => ({ Items: [], Total: 0 }), getRevenueSeries: async () => [] }))
const ids = ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222']
const parent = { ProductId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', Name: 'Điện thoại cùng sản phẩm', Status: 'Active', Category: { Name: 'Điện thoại' }, Brand: { Name: 'VIETECH' }, Description: null, WarrantyMonths: 12, Images: [] }
let notifications, variants, unavailable
const permissions = ['admin.portal', 'products:view']
const alert = (index) => ({ NotificationId: 'n' + index, Title: 'Cảnh báo tồn kho thấp ' + (index + 1), Content: 'Biến thể SKU-' + (index + 1) + ' còn 2 (ngưỡng cảnh báo 3).', NotificationType: 'LowStock', ReferenceType: 'ProductVariant', ReferenceId: ids[index], ActionUrl: null, CreatedAt: '2026-10-15T08:00:00Z', IsRead: false })
beforeEach(() => {
  vi.resetAllMocks(); unavailable = false
  notifications = [alert(0), alert(1)]
  variants = ids.map((id, i) => ({ ...parent, ProductVariantId: id, Sku: 'SKU-' + (i + 1), Color: i === 0 ? 'Đen' : 'Trắng', Price: '1000000.00', StockQuantity: i === 0 ? 2 : 20, MinStockLevel: 3, IsLowStock: i === 0, IsActive: true, VariantImages: [] }))
  api.getAdminData.mockImplementation(async (_, path) => {
    if (path === '/users/me/notifications/unread-count') return { Count: notifications.filter((n) => !n.IsRead).length }
    if (path === '/users/me/notifications') return { Items: structuredClone(notifications), Total: notifications.length }
    if (path === '/admin/variants') return { Items: structuredClone(variants), Total: variants.length }
    if (path === '/categories' || path === '/brands') return []
    const variant = variants.find((v) => path === '/admin/catalog-items/' + v.ProductVariantId)
    if (variant && !unavailable) return structuredClone(variant)
    throw new Error('Không tìm thấy sản phẩm.')
  })
  api.markNotificationRead.mockImplementation(async (_, id) => { notifications.find((n) => n.NotificationId === id).IsRead = true })
})
function open(role = 'Admin', path = '/admin/products?stock=low_stock') {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

test.each(['Admin', 'Staff'])('%s opens a reference-only stock notification at the correct SKU and marks only that notification read', async (role) => {
  const router = open(role)
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  const menu = within(await screen.findByRole('region', { name: 'Danh sách thông báo' }))
  const title = await menu.findByRole('link', { name: 'Mở thông báo: Cảnh báo tồn kho thấp 1' })
  expect(title).toHaveAttribute('href', '/admin/products?dialog=view&variant=' + ids[0])
  fireEvent.click(title)
  expect(screen.queryByRole('region', { name: 'Danh sách thông báo' })).not.toBeInTheDocument()
  const detail = within(await screen.findByRole('region', { name: 'Chi tiết sản phẩm' }, { timeout: 5000 }))
  expect(await detail.findByText('Mã sản phẩm: SKU-1')).toBeInTheDocument()
  expect(detail.queryByText('Mã sản phẩm: SKU-2')).not.toBeInTheDocument()
  expect(detail.getByText('2 sản phẩm')).toBeInTheDocument()
  expect(detail.getByText('Ngưỡng cảnh báo: 3')).toBeInTheDocument()
  expect(router.state.location.search).toBe('?dialog=view&variant=' + ids[0])
  await waitFor(() => expect(api.markNotificationRead).toHaveBeenCalledExactlyOnceWith('access-for-test', 'n0'))
  await screen.findByText('1 thông báo chưa đọc')
})

test('an old stock alert opens current server data for its sibling variant after restocking', async () => {
  open()
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  const menu = within(await screen.findByRole('region', { name: 'Danh sách thông báo' }))
  const item = (await menu.findByText('Cảnh báo tồn kho thấp 2')).closest('li')
  fireEvent.click(within(item).getByRole('link', { name: 'Xem chi tiết' }))
  const detail = within(await screen.findByRole('region', { name: 'Chi tiết sản phẩm' }))
  expect(await detail.findByText('Mã sản phẩm: SKU-2')).toBeInTheDocument()
  expect(detail.getByText('20 sản phẩm')).toBeInTheDocument()
  expect(detail.getByText('Còn hàng')).toBeInTheDocument()
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/catalog-items/' + ids[1], {}, expect.any(AbortSignal))
})

test('an already-read notification navigates without another mark request', async () => {
  notifications[0].IsRead = true
  open()
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  fireEvent.click(await screen.findByRole('link', { name: 'Mở thông báo: Cảnh báo tồn kho thấp 1' }))
  await screen.findByText('Mã sản phẩm: SKU-1')
  expect(api.markNotificationRead).not.toHaveBeenCalled()
})

test('mark-read failure does not prevent viewing the actual product', async () => {
  api.markNotificationRead.mockRejectedValue(new Error('Chưa đánh dấu được thông báo.'))
  open()
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  fireEvent.click(await screen.findByRole('link', { name: 'Mở thông báo: Cảnh báo tồn kho thấp 1' }))
  await screen.findByText('Mã sản phẩm: SKU-1')
  expect(notifications[0].IsRead).toBe(false)
  const failure = within(await screen.findByRole('alert', { name: 'Không đánh dấu được thông báo' }))
  expect(failure.getByText('Chưa đánh dấu được thông báo.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  expect(failure.getByText('Chưa đánh dấu được thông báo.')).toBeInTheDocument()
  api.markNotificationRead.mockImplementation(async (_, id) => { notifications.find(n => n.NotificationId === id).IsRead = true })
  fireEvent.click(failure.getByRole('button', { name: 'Thử lại' }))
  await waitFor(() => expect(screen.queryByRole('alert', { name: 'Không đánh dấu được thông báo' })).not.toBeInTheDocument())
  expect(notifications[0].IsRead).toBe(true)
  expect(api.markNotificationRead).toHaveBeenCalledTimes(2)
})

test('an unavailable variant shows an error and a usable return to the list', async () => {
  unavailable = true
  const router = open()
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  fireEvent.click(await screen.findByRole('link', { name: 'Mở thông báo: Cảnh báo tồn kho thấp 1' }))
  await screen.findByText('Không tìm thấy sản phẩm.')
  expect(screen.queryByRole('region', { name: 'Chi tiết sản phẩm' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Quay lại', exact: true }))
  await screen.findByRole('table', { name: '' })
  expect(router.state.location.pathname).toBe('/admin/products')
  expect(router.state.location.search).not.toContain('dialog=')
})

test('focus refresh updates the open notification list; references do not create local notifications', async () => {
  render(<AuthContext.Provider value={makeAuth({ role: 'Staff', permissions })}><MemoryRouter><AdminNotifications /></MemoryRouter></AuthContext.Provider>)
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  await screen.findByText('Cảnh báo tồn kho thấp 1')
  notifications = [{ ...alert(1), Title: 'Cảnh báo mới từ server' }]
  fireEvent(window, new Event('focus'))
  await screen.findByText('Cảnh báo mới từ server')
  expect(screen.queryByText('Cảnh báo tồn kho thấp 1')).not.toBeInTheDocument()
  expect(api.markNotificationRead).not.toHaveBeenCalled()
})

test('stock notification references cannot bypass product-view permission', async () => {
  render(<AuthContext.Provider value={makeAuth({ role: 'Staff', permissions: ['admin.portal'] })}><MemoryRouter><AdminNotifications /></MemoryRouter></AuthContext.Provider>)
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  await screen.findByText('Cảnh báo tồn kho thấp 1')
  expect(within(screen.getByRole('region', { name: 'Danh sách thông báo' })).queryByRole('link')).not.toBeInTheDocument()
})

test.each(['Admin', 'Staff'])('%s opening a second notification while the first is pending marks both read', async role => {
  let finish
  api.markNotificationRead.mockImplementationOnce((_, id) => new Promise(resolve => { finish = () => {
    notifications.find(n => n.NotificationId === id).IsRead = true; resolve()
  } }))
  open(role)
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  const menu = within(await screen.findByRole('region', { name: 'Danh sách thông báo' }))
  const first = (await menu.findByText('Cảnh báo tồn kho thấp 1')).closest('li')
  fireEvent.click(within(first).getByRole('button', { name: 'Đánh dấu đã đọc' }))
  await waitFor(() => expect(api.markNotificationRead).toHaveBeenCalledTimes(1))
  fireEvent.click(menu.getByRole('link', { name: 'Mở thông báo: Cảnh báo tồn kho thấp 2' }))
  await screen.findByText('Mã sản phẩm: SKU-2')
  await waitFor(() => expect(api.markNotificationRead).toHaveBeenCalledWith('access-for-test', 'n1'))
  await act(async () => finish())
  expect(notifications.every(n => n.IsRead)).toBe(true)
})

test('repeat activation of the same pending notification sends only one request', async () => {
  let finish
  api.markNotificationRead.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  open()
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  const menu = within(await screen.findByRole('region', { name: 'Danh sách thông báo' }))
  const row = (await menu.findByText('Cảnh báo tồn kho thấp 1')).closest('li')
  fireEvent.click(within(row).getByRole('button', { name: 'Đánh dấu đã đọc' }))
  fireEvent.click(menu.getByRole('link', { name: 'Mở thông báo: Cảnh báo tồn kho thấp 1' }))
  await screen.findByText('Mã sản phẩm: SKU-1')
  expect(api.markNotificationRead).toHaveBeenCalledTimes(1)
  await act(async () => finish())
})

test.each(['Admin', 'Staff'])('%s refreshes a cached chat alert target before navigating', async role => {
  notifications = [{ ...alert(0), NotificationType: 'Chat', ReferenceType: 'Conversation', ActionUrl: '/admin/support?conversation=' + ids[0], Title: 'Khách đang chờ' }]
  api.markNotificationRead.mockResolvedValue({ ...notifications[0], IsRead: true, ActionUrl: '/admin/support' })
  const router = createMemoryRouter([{ path: '/admin', element: <AdminNotifications /> }, { path: '/admin/support', element: <p>Hàng đợi hỗ trợ</p> }], { initialEntries: ['/admin'] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions: ['admin.portal', 'chat:view'] })}><RouterProvider router={router} /></AuthContext.Provider>)
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  const link = await screen.findByRole('link', { name: 'Mở thông báo: Khách đang chờ' })
  expect(link).toHaveAttribute('href', '/admin/support')  // Safe fallback for opening in another tab.
  fireEvent.click(link)
  await screen.findByText('Hàng đợi hỗ trợ')
  expect(router.state.location.search).toBe('')
  expect(api.markNotificationRead).toHaveBeenCalledExactlyOnceWith('access-for-test', 'n0')
})
