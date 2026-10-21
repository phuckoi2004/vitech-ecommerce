import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import AdminNotifications from './AdminNotifications.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn(), markNotificationRead: vi.fn(), markAllNotificationsRead: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
let notifications

beforeEach(() => {
  vi.resetAllMocks()
  notifications = [1, 2].map(id => ({
    NotificationId: 'n' + id, Title: 'Đơn mới ' + id, Content: 'Chờ xác nhận',
    NotificationType: 'NewOrder', ReferenceType: 'Order',
    ReferenceId: `${id}1111111-1111-4111-8111-111111111111`,
    ActionUrl: `/admin/orders/${id}1111111-1111-4111-8111-111111111111`,
    IsRead: false, CreatedAt: '2026-10-21T08:00:00Z',
  }))
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path.endsWith('/unread-count')) return { Count: notifications.filter(note => !note.IsRead).length }
    const items = notifications.filter(note => query.is_read !== false || !note.IsRead)
    return { Items: structuredClone(items), Total: items.length }
  })
  api.markNotificationRead.mockImplementation(async (_, id) => { notifications.find(note => note.NotificationId === id).IsRead = true })
  api.markAllNotificationsRead.mockImplementation(async () => { notifications.forEach(note => { note.IsRead = true }) })
})
afterEach(() => { vi.useRealTimers() })

function open(path = '/admin') {
  const router = createMemoryRouter([{
    path: '/admin', element: <><AdminNotifications navigateToPage /><Outlet /></>,
    children: [
      { index: true, element: <p>Trang quản trị</p> },
      { path: 'notifications', element: <div id="admin-notifications-page" /> },
      { path: 'orders/:orderId', element: <p>Chi tiết đơn hàng</p> },
    ],
  }], { initialEntries: [path] })
  const rendered = render(<AuthContext.Provider value={makeAuth({ role: 'Staff', permissions: ['admin.portal', 'orders:view'] })}><RouterProvider router={router} /></AuthContext.Provider>)
  return { router, ...rendered }
}

function dot() { return screen.getByRole('button', { name: 'Thông báo' }).querySelector('.bg-admin-red') }
const countRequests = () => api.getAdminData.mock.calls.filter(([, path]) => path.endsWith('/unread-count')).length

test('the bell keeps a visible static red dot and opens the separate page without marking notices read', async () => {
  const { router } = open()
  await screen.findByText('2 thông báo chưa đọc')
  expect(dot()).toBeVisible()
  expect(dot()).not.toHaveClass('animate-pulse')
  fireEvent.click(screen.getByRole('button', { name: 'Thông báo' }))
  const page = await screen.findByRole('region', { name: 'Danh sách thông báo' })
  expect(router.state.location.pathname).toBe('/admin/notifications')
  expect(await within(page).findByText('Đơn mới 1')).toBeVisible()
  expect(dot()).toBeVisible()
  expect(api.markNotificationRead).not.toHaveBeenCalled()
  expect(api.markAllNotificationsRead).not.toHaveBeenCalled()
  fireEvent.click(within(page).getByRole('button', { name: 'Chưa đọc' }))
  await waitFor(() => expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/users/me/notifications', { page: 1, page_size: 20, is_read: false }, expect.any(AbortSignal)))
})

test('reading one notice preserves the dot for other unread notices; reading all clears it immediately', async () => {
  open('/admin/notifications')
  const page = await screen.findByRole('region', { name: 'Danh sách thông báo' })
  await within(page).findByText('Đơn mới 1')
  fireEvent.click(within(page).getAllByRole('button', { name: 'Đánh dấu đã đọc' })[0])
  await screen.findByText('1 thông báo chưa đọc')
  expect(notifications.map(note => note.IsRead)).toEqual([true, false])
  expect(dot()).toBeVisible()
  fireEvent.click(within(page).getByRole('button', { name: 'Đọc tất cả' }))
  await waitFor(() => expect(dot()).toBeNull())
  expect(notifications.every(note => note.IsRead)).toBe(true)
})

test.each(['admin-order-updated', 'focus'])('%s refreshes both the dot and the open page immediately', async eventName => {
  open('/admin/notifications')
  const page = await screen.findByRole('region', { name: 'Danh sách thông báo' })
  await within(page).findByText('Đơn mới 1')
  notifications[0].IsRead = true // The server acknowledged this order; another unread order remains.
  act(() => window.dispatchEvent(new Event(eventName)))
  await screen.findByText('1 thông báo chưa đọc')
  await within(page).findByText('Đã đọc')
  expect(dot()).toBeVisible()
  notifications[1].IsRead = true
  act(() => window.dispatchEvent(new Event(eventName)))
  await waitFor(() => expect(dot()).toBeNull())
  expect(api.markNotificationRead).not.toHaveBeenCalled()
})

test('background changes are checked at 60 seconds and polling stops after unmount', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const { unmount } = open()
  await screen.findByText('2 thông báo chưa đọc')
  notifications.forEach(note => { note.IsRead = true })
  await act(async () => { await vi.advanceTimersByTimeAsync(59999) })
  expect(countRequests()).toBe(1)
  expect(dot()).toBeVisible()
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  await waitFor(() => expect(dot()).toBeNull())
  expect(countRequests()).toBe(2)
  unmount()
  await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
  expect(countRequests()).toBe(2)
})

test('the dot stays visible while a refresh is waiting for the unread count', async () => {
  open()
  await screen.findByText('2 thông báo chưa đọc')
  let finish
  api.getAdminData.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  act(() => window.dispatchEvent(new Event('admin-order-updated')))
  await waitFor(() => expect(finish).toBeTypeOf('function'))
  expect(dot()).toBeVisible()
  await act(async () => { finish({ Count: 0 }) })
  expect(dot()).toBeNull()
})
