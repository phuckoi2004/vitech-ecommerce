import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import { adminRoutes } from '../routes/index.jsx'

const api = vi.hoisted(() => ({ getAdminData: vi.fn() }))
vi.mock('../../services/api/admin.js', () => api)
const item = { WarrantyRequestId: 'w0', RequestCode: 'BH-0', CustomerName: 'Nguyễn Văn An', ProductName: 'Điện thoại đen', Sku: 'PHONE-BLACK', VariantInfo: 'Đen / 256 GB', SerialNumber: '359812345678712', OrderCode: 'DH-123', IssueDescription: 'Màn hình bị lỗi', Status: 'New', EligibilityStatus: 'Pending', RequestedAt: '2026-10-15T03:00:00Z', ReceivedAt: null, ResultApprovedAt: null, Attachments: [], Histories: [] }
let rows
function renderPage(path = '/admin/warranties', role = 'Admin', permissions = ['admin.portal', 'warranties:view']) {
  const router = createMemoryRouter(adminRoutes, { initialEntries: [path] })
  render(<AuthContext.Provider value={makeAuth({ role, permissions })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
const tableRows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1).map((row) => row.cells[0].textContent)
beforeEach(() => {
  vi.resetAllMocks(); rows = []
  api.getAdminData.mockImplementation(async (_, path, query) => {
    if (path === '/users/me/notifications/unread-count') return { Count: 0 }
    if (path === '/admin/warranty-requests') return { Items: structuredClone(rows.slice((query.page - 1) * query.page_size, query.page * query.page_size)), Total: rows.length }
    const found = rows.find((row) => path === '/admin/warranty-requests/' + row.WarrantyRequestId)
    if (found) return structuredClone(found)
    throw new Error('Không tìm thấy yêu cầu bảo hành.')
  })
})

test('empty list keeps all Figma columns, accurate zero counts and selected sidebar entry', async () => {
  renderPage()
  await screen.findByText('Chưa có yêu cầu bảo hành.')
  expect(screen.getByRole('heading', { level: 1, name: 'Quản lý bảo hành' })).toBeInTheDocument()
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Mã yêu cầu', 'Khách hàng', 'Sản phẩm', 'Serial/IMEI', 'Ngày gửi', 'Trạng thái', 'Thao tác'])
  expect(screen.getByText('0 yêu cầu')).toBeInTheDocument()
  expect(screen.getByText('Hiển thị 0–0 trong 0 yêu cầu')).toBeInTheDocument()
  expect(within(screen.getByRole('navigation', { name: 'Menu quản trị' })).getByRole('button', { name: 'Bảo hành', exact: true })).toHaveAttribute('aria-current', 'page')
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Chưa áp dụng' } })
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  expect(screen.getByRole('searchbox')).toHaveValue('')
})

test('latest first across every API page; pagination is applied after sorting', async () => {
  rows = Array.from({ length: 101 }, (_, i) => ({ ...item, WarrantyRequestId: 'w' + i, RequestCode: 'BH-' + i, RequestedAt: '2026-10-10T03:00:00Z' }))
  rows[100] = { ...rows[100], Status: 'Rejected', RequestedAt: '2026-10-15T03:00:00Z' }
  renderPage()
  await screen.findByText('101 yêu cầu')
  expect(api.getAdminData).toHaveBeenCalledWith('access-for-test', '/admin/warranty-requests', { page: 2, page_size: 100 }, expect.any(AbortSignal))
  expect(tableRows()[0]).toBe('BH-100')
  expect(tableRows()).toHaveLength(6)
})

test('UI stages follow reception and approved result data without changing backend statuses', async () => {
  rows = [item,
    { ...item, WarrantyRequestId: 'w1', RequestCode: 'BH-1', ReceivedAt: '2026-10-15T04:00:00Z' },
    { ...item, WarrantyRequestId: 'w2', RequestCode: 'BH-2', Status: 'HandedOver' },
    { ...item, WarrantyRequestId: 'w3', RequestCode: 'BH-3', Status: 'Processing', ResultType: 'Repaired', ResultProposedAt: '2026-10-15T05:00:00Z' },
    { ...item, WarrantyRequestId: 'w4', RequestCode: 'BH-4', Status: 'Processing', ResultType: 'Repaired', ResultApprovedAt: '2026-10-15T06:00:00Z' },
    { ...item, WarrantyRequestId: 'w5', RequestCode: 'BH-5', Status: 'Completed' }]
  renderPage('/admin/warranties', 'Staff')
  await screen.findByText('6 yêu cầu')
  const cells = within(screen.getByRole('table')).getAllByRole('row').slice(1).map((row) => row.cells[5].textContent)
  expect(cells).toEqual(['Mới', 'Đang kiểm tra', 'Đang sửa', 'Đang sửa', 'Hoàn tất', 'Đã trả khách'])
  fireEvent.click(screen.getByRole('button', { name: 'Đang sửa', exact: true }))
  await screen.findByText('2 yêu cầu')
  expect(tableRows()).toEqual(['BH-2', 'BH-3'])
  expect(screen.getByRole('combobox', { name: 'Trạng thái', exact: true })).toHaveValue('Repairing')
  fireEvent.click(screen.getByRole('button', { name: 'Hoàn tất', exact: true }))
  await screen.findByText('1 yêu cầu')
  expect(tableRows()).toEqual(['BH-4'])
})

test('search matches the original IMEI even though list display is masked; absent serial stays empty', async () => {
  rows = [item, { ...item, WarrantyRequestId: 'w1', RequestCode: 'BH-1', SerialNumber: null }]
  renderPage()
  await screen.findByText('2 yêu cầu')
  expect(screen.getByText('3598••••8712')).toBeInTheDocument()
  expect(screen.queryByText('359812345678712')).not.toBeInTheDocument()
  expect(within(screen.getByRole('table')).getByText('—')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '359812345678712' } })
  expect(screen.queryByRole('button', { name: 'Tìm kiếm', exact: true })).not.toBeInTheDocument()
  await screen.findByText('1 yêu cầu')
  expect(tableRows()).toEqual(['BH-0'])
})

test('accent-insensitive customer search and inclusive Vietnam dates combine automatically', async () => {
  rows = [item, { ...item, WarrantyRequestId: 'w1', RequestCode: 'BH-1', RequestedAt: '2026-10-14T17:00:00Z' }]
  const router = renderPage('/admin/warranties?page=2')
  await screen.findByText('2 yêu cầu')
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'nguyen van an' } })
  fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2026-10-15' } })
  fireEvent.change(screen.getByLabelText('Đến ngày'), { target: { value: '2026-10-15' } })
  await waitFor(() => expect(router.state.location.search).toContain('keyword=nguyen+van+an'))
  expect(tableRows()).toEqual(['BH-0', 'BH-1'])
  expect(router.state.location.search).not.toContain('page=')
  fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2026-10-16' } })
  expect(screen.getByRole('alert')).toHaveTextContent('Từ ngày không được sau Đến ngày.')
  expect(screen.queryByRole('button', { name: 'Tìm kiếm', exact: true })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Xóa lọc' }))
  expect(screen.getByRole('searchbox')).toHaveValue('')
  expect(screen.getByLabelText('Từ ngày')).toHaveValue('')
})

test('detail opens selected request under the same sidebar; back preserves filters', async () => {
  rows = [item]
  const router = renderPage('/admin/warranties?keyword=BH-0&status=New')
  fireEvent.click(await screen.findByRole('button', { name: 'Xem chi tiết BH-0' }))
  await screen.findByRole('heading', { level: 1, name: 'Chi tiết bảo hành' })
  await screen.findByText('Màn hình bị lỗi')
  expect(router.state.location.pathname).toBe('/admin/warranties/w0')
  expect(screen.getByText('3598••••8712')).toHaveAttribute('title', '359812345678712')
  expect(screen.getByText('DH-123')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '← Danh sách bảo hành' }))
  await screen.findByRole('button', { name: 'Xem chi tiết BH-0' })
  expect(router.state.location.search).toBe('?keyword=BH-0&status=New')
})

test('failed later API page shows an error instead of partial data; retry and refresh work', async () => {
  rows = Array.from({ length: 101 }, (_, i) => ({ ...item, WarrantyRequestId: 'w' + i, RequestCode: 'BH-' + i }))
  const original = api.getAdminData.getMockImplementation()
  let failed = true
  api.getAdminData.mockImplementation((...args) => args[1] === '/admin/warranty-requests' && args[2].page === 2 && failed ? Promise.reject(new Error('Lỗi trang thứ hai.')) : original(...args))
  renderPage()
  await screen.findByText('Lỗi trang thứ hai.')
  expect(screen.queryByText('101 yêu cầu')).not.toBeInTheDocument()
  failed = false; fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  await screen.findByText('101 yêu cầu')
  rows = []
  fireEvent.click(screen.getByRole('button', { name: 'Làm mới' }))
  await screen.findByText('Chưa có yêu cầu bảo hành.')
})

test('missing permission prevents detail API reads', async () => {
  renderPage('/admin/warranties/w0', 'Staff', ['admin.portal'])
  await screen.findByRole('heading', { name: 'Không có quyền truy cập' })
  expect(api.getAdminData.mock.calls.some((call) => call[1].startsWith('/admin/warranty-requests'))).toBe(false)
})

test('unavailable request shows an error and a working back action', async () => {
  renderPage('/admin/warranties/missing')
  await screen.findByText('Không tìm thấy yêu cầu bảo hành.')
  expect(screen.queryByText('Serial/IMEI')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '← Danh sách bảo hành' }))
  await screen.findByText('Chưa có yêu cầu bảo hành.')
})
