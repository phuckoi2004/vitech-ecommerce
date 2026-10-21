import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../../auth/context.js'
import { makeAuth } from '../../../test/auth.js'
import WarrantyHistory from './WarrantyHistory.jsx'

const api = vi.hoisted(() => ({ listMyWarranties: vi.fn(), getMyWarranty: vi.fn(), cancelWarranty: vi.fn() }))
vi.mock('../../../lib/warranty-api.js', () => api)

const request = { WarrantyRequestId: 'w1', RequestCode: 'BH-001', ProductName: 'Điện thoại VieTech', VariantInfo: 'Đen / 256GB',
  OrderId: 'o1', OrderCode: 'DH-001', SerialNumber: 'IMEI-001', Status: 'New', ReceivedAt: null, RequestedAt: '2026-10-20T05:00:00Z',
  IssueDescription: 'Máy không lên nguồn', ResultApprovedAt: null, ResultType: null, Attachments: [],
  Histories: [{ ServiceRequestHistoryId: 'h1', ChangedAt: '2026-10-20T05:00:00Z', NewStatus: 'New', Note: 'Khách hàng gửi yêu cầu.' }] }

function mount(search = '') {
  const router = createMemoryRouter([{ path: '/tai-khoan', element: <WarrantyHistory /> }], { initialEntries: ['/tai-khoan?section=service' + search] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Customer' })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
beforeEach(() => {
  vi.resetAllMocks()
  api.listMyWarranties.mockResolvedValue({ Items: [request], Total: 1 })
  api.getMyWarranty.mockResolvedValue(request)
})

test('lists own warranty requests and opens their real customer detail', async () => {
  const router = mount()
  await screen.findByText('BH-001')
  expect(screen.getByText('Điện thoại VieTech')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '+ Tạo yêu cầu bảo hành' })).toHaveAttribute('href', '/bao-hanh/tao-yeu-cau')
  await userEvent.click(screen.getByRole('link', { name: 'Xem chi tiết →' }))
  await screen.findByRole('heading', { name: 'Yêu cầu BH-001' })
  expect(router.state.location.search).toContain('request=w1')
  expect(api.getMyWarranty).toHaveBeenCalledWith('access-for-test', 'w1', expect.anything())
  expect(screen.getByText('Khách hàng gửi yêu cầu.')).toBeInTheDocument()
})

test.each([
  [{ Status: 'New', ReceivedAt: '2026-10-20T06:00:00Z' }, 'Đang kiểm tra'],
  [{ Status: 'Processing' }, 'Đang sửa'],
  [{ Status: 'Processing', ResultApprovedAt: '2026-10-20T07:00:00Z' }, 'Hoàn tất'],
  [{ Status: 'Completed' }, 'Đã trả khách'],
])('uses the same stage as admin and disallows cancellation after receipt: %s', async (extra, label) => {
  api.getMyWarranty.mockResolvedValue({ ...request, ...extra })
  mount('&request=w1')
  expect(await screen.findByText(label)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Hủy yêu cầu bảo hành' })).not.toBeInTheDocument()
})

test('requires explicit cancellation confirmation and reloads the saved state', async () => {
  api.cancelWarranty.mockResolvedValue({ ...request, Status: 'Cancelled' })
  api.getMyWarranty.mockResolvedValueOnce(request).mockResolvedValueOnce({ ...request, Status: 'Cancelled' })
  mount('&request=w1')
  await userEvent.click(await screen.findByRole('button', { name: 'Hủy yêu cầu bảo hành' }))
  expect(api.cancelWarranty).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận hủy' }))
  expect(await screen.findByText('Đã hủy')).toBeInTheDocument()
  expect(api.cancelWarranty).toHaveBeenCalledWith('access-for-test', 'w1')
})

test('handles a concurrent admin receipt by refreshing and removing the cancel action', async () => {
  api.cancelWarranty.mockRejectedValue(Object.assign(new Error('Đã tiếp nhận sản phẩm.'), { code: 'warranty_not_cancellable' }))
  api.getMyWarranty.mockResolvedValueOnce(request).mockResolvedValueOnce({ ...request, ReceivedAt: '2026-10-20T06:00:00Z' })
  mount('&request=w1')
  await userEvent.click(await screen.findByRole('button', { name: 'Hủy yêu cầu bảo hành' }))
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận hủy' }))
  expect(await screen.findByText('Đang kiểm tra')).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('Đã tiếp nhận sản phẩm.')
  expect(screen.queryByRole('button', { name: 'Hủy yêu cầu bảo hành' })).not.toBeInTheDocument()
})

test('never renders unpublished results; manual refresh shows the result the operator published', async () => {
  api.getMyWarranty.mockResolvedValueOnce({ ...request, Status: 'Processing', ResultType: 'Repaired', ResultNote: 'PRIVATE-PENDING' })
    .mockResolvedValueOnce({ ...request, Status: 'Processing', ResultType: 'Repaired', ResultNote: 'Thay cáp màn hình', ResultApprovedAt: '2026-10-20T07:00:00Z' })
  mount('&request=w1')
  await screen.findByText('Đang sửa')
  expect(screen.queryByText('PRIVATE-PENDING')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Làm mới tiến trình' }))
  expect(await screen.findByText('Thay cáp màn hình')).toBeInTheDocument()
})

test('filters and paginates the server list using URL state', async () => {
  api.listMyWarranties.mockResolvedValue({ Items: [request], Total: 14 })
  const router = mount()
  await screen.findByText('BH-001')
  await userEvent.click(screen.getByRole('button', { name: 'Sau' }))
  await waitFor(() => expect(api.listMyWarranties).toHaveBeenLastCalledWith('access-for-test', expect.objectContaining({ page: 2 }), expect.anything()))
  await userEvent.selectOptions(screen.getByLabelText('Trạng thái bảo hành'), 'Rejected')
  await waitFor(() => expect(api.listMyWarranties).toHaveBeenLastCalledWith('access-for-test', expect.objectContaining({ page: 1, status: 'Rejected' }), expect.anything()))
  expect(router.state.location.search).not.toContain('warrantyPage')
})
