import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../../auth/context.js'
import { makeAuth } from '../../../test/auth.js'
import ReturnHistory from './ReturnHistory.jsx'

const api = vi.hoisted(() => ({ listMyReturns: vi.fn(), getMyReturn: vi.fn(), cancelReturn: vi.fn() }))
vi.mock('../../../lib/return-api.js', () => api)
const request = { ReturnRequestId: 'r1', RequestCode: 'DT-001', ProductName: 'Điện thoại VieTech', VariantInfo: 'Đen / 256GB',
  OrderId: 'o1', OrderCode: 'DH-001', SerialNumber: 'IMEI-001', RequestType: 'Return', Quantity: 1, Status: 'Pending',
  ReceivedAt: null, RequestedAt: '2026-10-20T05:00:00Z', Reason: 'Máy không lên nguồn', CompensationAmount: null,
  CompensationApprovedAt: null, Attachments: [], Histories: [{ ServiceRequestHistoryId: 'h1', ChangedAt: '2026-10-20T05:00:00Z', NewStatus: 'Pending', Note: 'Khách hàng gửi yêu cầu.' }] }
function mount(search = '') {
  const router = createMemoryRouter([{ path: '/tai-khoan', element: <ReturnHistory /> }], { initialEntries: ['/tai-khoan?section=service&type=return' + search] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Customer' })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
beforeEach(() => {
  vi.resetAllMocks()
  api.listMyReturns.mockResolvedValue({ Items: [request], Total: 1 })
  api.getMyReturn.mockResolvedValue(request)
})

test('lists and opens the customer return detail, preserving its request type in the route', async () => {
  const router = mount()
  await screen.findByText('DT-001')
  expect(screen.getByRole('link', { name: '+ Tạo yêu cầu đổi/trả' })).toHaveAttribute('href', '/doi-tra/tao-yeu-cau')
  await userEvent.click(screen.getByRole('link', { name: 'Xem chi tiết →' }))
  expect(await screen.findByRole('heading', { name: 'Yêu cầu DT-001' })).toBeInTheDocument()
  expect(router.state.location.search).toBe('?section=service&type=return&request=r1')
  expect(api.getMyReturn).toHaveBeenCalledWith('access-for-test', 'r1', expect.anything())
  expect(screen.getByText('Khách hàng gửi yêu cầu.')).toBeInTheDocument()
})

test('cancels only after confirmation and reloads the saved state', async () => {
  api.cancelReturn.mockResolvedValue({ ...request, Status: 'Cancelled' })
  api.getMyReturn.mockResolvedValueOnce(request).mockResolvedValueOnce({ ...request, Status: 'Cancelled' })
  mount('&request=r1')
  await userEvent.click(await screen.findByRole('button', { name: 'Hủy yêu cầu đổi/trả' }))
  expect(api.cancelReturn).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận hủy' }))
  expect(await screen.findByText('Đã hủy')).toBeInTheDocument()
  expect(api.cancelReturn).toHaveBeenCalledWith('access-for-test', 'r1')
})

test.each(['Approved', 'Receiving', 'Processing', 'Completed', 'Rejected', 'Cancelled'])('prevents customer cancellation at %s', async (Status) => {
  api.getMyReturn.mockResolvedValue({ ...request, Status })
  mount('&request=r1')
  await screen.findByRole('heading', { name: 'Yêu cầu DT-001' })
  expect(screen.queryByRole('button', { name: 'Hủy yêu cầu đổi/trả' })).not.toBeInTheDocument()
})

test('concurrent admin acceptance refreshes the request and removes the cancellation action', async () => {
  api.cancelReturn.mockRejectedValue(Object.assign(new Error('Yêu cầu đã được tiếp nhận.'), { code: 'return_not_cancellable' }))
  api.getMyReturn.mockResolvedValueOnce(request).mockResolvedValueOnce({ ...request, Status: 'Approved' })
  mount('&request=r1')
  await userEvent.click(await screen.findByRole('button', { name: 'Hủy yêu cầu đổi/trả' }))
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận hủy' }))
  expect(await screen.findByText('Đã tiếp nhận')).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('Yêu cầu đã được tiếp nhận.')
  expect(screen.queryByRole('button', { name: 'Hủy yêu cầu đổi/trả' })).not.toBeInTheDocument()
})

test('completion never implies a refund and unapproved amounts remain hidden', async () => {
  api.getMyReturn.mockResolvedValue({ ...request, Status: 'Completed', CompensationAmount: '999999999.00' })
  mount('&request=r1')
  await screen.findByText('Đã trả máy')
  expect(screen.queryByText(/999/)).not.toBeInTheDocument()
  expect(screen.getByText(/không có nghĩa đã hoàn tiền/)).toBeInTheDocument()
})

test('filters and pagination use server statuses and reset the page on filter changes', async () => {
  api.listMyReturns.mockResolvedValue({ Items: [request], Total: 14 })
  const router = mount()
  await screen.findByText('DT-001')
  await userEvent.click(screen.getByRole('button', { name: 'Sau' }))
  await waitFor(() => expect(api.listMyReturns).toHaveBeenLastCalledWith('access-for-test', expect.objectContaining({ page: 2 }), expect.anything()))
  await userEvent.selectOptions(screen.getByLabelText('Trạng thái đổi/trả'), 'Rejected')
  await waitFor(() => expect(api.listMyReturns).toHaveBeenLastCalledWith('access-for-test', expect.objectContaining({ page: 1, status: 'Rejected' }), expect.anything()))
  expect(router.state.location.search).not.toContain('returnPage')
})
