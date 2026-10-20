import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
const item = { ReturnRequestId: 'r0', RequestCode: 'RT-0', CustomerName: 'Nguyễn Văn An', ProductName: 'Điện thoại đen', Sku: 'PHONE-BLACK', VariantInfo: 'Đen / 256 GB', OrderCode: 'DH-123', Quantity: 1, RequestType: 'Return', Reason: 'Màn hình bị lỗi', Status: 'Approved', RequestedAt: '2026-10-15T03:00:00Z', ReceivedAt: null, Attachments: [], Histories: [] }
let rows
function renderPage(path = '/admin/returns', role = 'Admin', permissions = ['admin.portal', 'returns:view']) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
const tableRows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1).map((row) => row.cells[0].textContent)
beforeEach(() => {
  vi.resetAllMocks(); rows = []
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/return-requests') return { Items: structuredClone(rows.slice((query.page - 1) * query.page_size, query.page * query.page_size)), Total: rows.length }
    const found = rows.find((row) => path === '/admin/return-requests/' + row.ReturnRequestId)
    if (found) return structuredClone(found)
    throw new Error('Không tìm thấy yêu cầu đổi trả.')
  })
})

test('empty returns retain all columns and true counts; admin menu and header are connected', async () => {
  renderPage()
  await screen.findByText('Chưa có yêu cầu đổi trả.')
  expect(screen.getByRole('heading', { level: 1, name: 'Quản lý đổi trả' })).toBeInTheDocument()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Mã yêu cầu', 'Khách hàng', 'Sản phẩm', 'Loại yêu cầu', 'Ngày gửi', 'Trạng thái', 'Thao tác'])
  expect(screen.getByText('0 yêu cầu')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 yêu cầu')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Chưa áp dụng' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  expect(screen.getByRole('searchbox')).toHaveValue('')
  expect(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Đổi trả', exact: true })).toHaveAttribute('aria-current', 'page')
})

test('waiting requests on later API pages precede newer nonwaiting records before UI pagination', async () => {
  rows = Array.from({ length: 102 }, (_, i) => ({ ...item, ReturnRequestId: 'r' + i, RequestCode: 'RT-' + i, RequestedAt: '2026-10-15T03:00:00Z' }))
  rows[100] = { ...rows[100], Status: 'Pending', RequestedAt: '2026-09-01T03:00:00Z' }
  rows[101] = { ...rows[101], Status: 'Pending', RequestedAt: '2026-09-02T03:00:00Z' }
  renderPage()
  await screen.findByText('102 yêu cầu')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/return-requests', { page: 2, page_size: 100, pending_first: true }, expect.any(AbortSignal))
  expect(tableRows().slice(0, 2)).toEqual(['RT-101', 'RT-100'])
  expect(tableRows()).toHaveLength(6)
})

test('newest first within each group, quick status filter and staff read access', async () => {
  rows = [item, { ...item, ReturnRequestId: 'r1', RequestCode: 'RT-1', Status: 'Pending', RequestedAt: '2026-10-10T03:00:00Z' }, { ...item, ReturnRequestId: 'r2', RequestCode: 'RT-2', Status: 'Pending', RequestedAt: '2026-10-11T03:00:00Z' }, { ...item, ReturnRequestId: 'r3', RequestCode: 'RT-3', Status: 'Rejected', RequestedAt: '2026-10-14T03:00:00Z' }]
  renderPage('/admin/returns', 'Staff')
  await screen.findByText('4 yêu cầu')
  expect(tableRows()).toEqual(['RT-2', 'RT-1', 'RT-0', 'RT-3'])
  fireEvent.click(screen.getByRole('button', { name: 'Đang chờ', exact: true }))
  await screen.findByText('2 yêu cầu')
  expect(tableRows()).toEqual(['RT-2', 'RT-1'])
  expect(screen.getByRole('combobox', { name: 'Trạng thái', exact: true })).toHaveValue('Pending')
})

test('accent-insensitive search and inclusive Vietnam dates apply automatically, reset pagination and clear', async () => {
  rows = [item, { ...item, ReturnRequestId: 'r1', RequestCode: 'RT-1', RequestedAt: '2026-10-14T17:00:00Z' }]
  const router = renderPage('/admin/returns?page=2')
  await screen.findByText('2 yêu cầu')
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'nguyen van an' } })
  fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2026-10-15' } })
  fireEvent.change(screen.getByLabelText('Đến ngày'), { target: { value: '2026-10-15' } })
  await waitFor(() => expect(router.state.location.search).toContain('keyword=nguyen+van+an'))
  expect(tableRows()).toEqual(['RT-0', 'RT-1'])
  expect(router.state.location.search).not.toContain('page=')
  fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2026-10-16' } })
  expect(screen.getByRole('alert')).toHaveTextContent('Từ ngày không được sau Đến ngày.')
  expect(screen.queryByRole('button', { name: 'Tìm kiếm', exact: true })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  expect(screen.getByRole('searchbox')).toHaveValue('')
  expect(screen.getByLabelText('Từ ngày')).toHaveValue('')
})

test('view detail fetches the chosen request and back preserves filters and page', async () => {
  rows = [item]
  const router = renderPage('/admin/returns?keyword=RT-0&status=Approved')
  fireEvent.click(await screen.findByRole('button', { name: 'Xem chi tiết RT-0' }))
  await screen.findByRole('heading', { level: 1, name: 'Chi tiết đổi trả' })
  await screen.findByText('Màn hình bị lỗi')
  expect(router.state.location.pathname).toBe('/admin/returns/r0')
  expect(screen.getByText('Điện thoại đen')).toHaveAttribute('title', 'PHONE-BLACK • Đen / 256 GB')
  expect(screen.getByText('DH-123')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '← Danh sách đổi trả' }))
  await screen.findByRole('button', { name: 'Xem chi tiết RT-0' })
  expect(router.state.location.search).toBe('?keyword=RT-0&status=Approved')
})

test('a failed later API page shows an error instead of partial totals; retry and refresh work', async () => {
  rows = Array.from({ length: 101 }, (_, i) => ({ ...item, ReturnRequestId: 'r' + i, RequestCode: 'RT-' + i }))
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/return-requests' && args[2].page === 2 && failed ? Promise.reject(new Error('Lỗi trang thứ hai.')) : original(...args))
  renderPage()
  await screen.findByText('Lỗi trang thứ hai.')
  expect(screen.queryByText('101 yêu cầu')).not.toBeInTheDocument()
  failed = false; fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('101 yêu cầu')
  rows = []
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByText('Chưa có yêu cầu đổi trả.')
})

test('missing permission prevents list and detail API reads', async () => {
  renderPage('/admin/returns/r0', 'Staff', ['admin.portal'])
  await screen.findByRole('heading', { name: 'Không có quyền truy cập' })
  expect(api.getAdminData.mock.calls.some((call) => call[1].startsWith('/admin/return-requests'))).toBe(false)
})
