import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import WarrantyCreatePage from './WarrantyCreatePage.jsx'

const api = vi.hoisted(() => ({ listMyOrders: vi.fn(), getWarrantyItems: vi.fn(), createWarranty: vi.fn(), uploadWarrantyImage: vi.fn(), getProduct: vi.fn() }))
vi.mock('../../lib/order-api.js', () => ({ listMyOrders: api.listMyOrders }))
vi.mock('../../lib/warranty-api.js', () => api)
vi.mock('../../lib/catalog-api.js', () => ({ getProduct: api.getProduct }))

const device = (id) => ({ ProductSerialId: id, SerialNumber: 'IMEI-' + id, CanRequest: true, Reason: null, WarrantyStartDate: '2026-10-01', WarrantyEndDate: '2027-09-30' })
const item = { OrderItemId: 'line1', ProductId: 'product1', ProductVariantId: 'variant1', ProductName: 'Điện thoại VieTech', VariantInfo: 'Đen / 256GB', Quantity: 2,
  WarrantyMonths: 12, IsSerialTracked: true, CanRequest: true, Serials: [device('s1'), device('s2')] }
const order = (id) => ({ OrderId: id, OrderCode: 'DH-' + id, OrderedAt: '2026-10-01T05:00:00Z', OrderStatus: 'Delivered' })

function mount() {
  const router = createMemoryRouter([{ path: '/new', element: <WarrantyCreatePage /> }, { path: '/tai-khoan', element: <p>Danh sách bảo hành</p> }], { initialEntries: ['/new'] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Customer' })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
async function chooseProduct(serial = 's2') {
  await screen.findByRole('option', { name: /DH-o1/ })
  await userEvent.selectOptions(screen.getByLabelText('Mã đơn hàng *'), 'o1')
  await screen.findByRole('option', { name: /Điện thoại VieTech/ })
  await userEvent.selectOptions(screen.getByLabelText('Sản phẩm cần bảo hành *'), 'line1')
  if (serial) await userEvent.selectOptions(screen.getByLabelText('Serial / IMEI *'), serial)
}
async function describe() {
  await userEvent.type(screen.getByLabelText('Mô tả tình trạng lỗi *'), 'Màn hình bị nhấp nháy khi sạc.')
  await userEvent.click(screen.getByRole('checkbox', { name: /Tôi xác nhận/ }))
}

beforeEach(() => {
  vi.resetAllMocks()
  api.listMyOrders.mockResolvedValue({ Items: [order('o1'), order('o2')], Total: 2 })
  api.getWarrantyItems.mockResolvedValue([item])
  api.createWarranty.mockResolvedValue({ WarrantyRequestId: 'request1', Status: 'New' })
  api.getProduct.mockResolvedValue({ Images: [{ ImageUrl: 'https://images.test/phone.png', SortOrder: 0 }], Variants: [] })
})

test('creates a request with exact assigned serial, order line, public description and uploaded evidence', async () => {
  const router = mount()
  await chooseProduct()
  expect(api.listMyOrders).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ order_status: ['Delivered', 'Completed'] }), expect.anything())
  expect(screen.getByLabelText('Thời hạn bảo hành')).toHaveValue('01/10/2026 – 30/09/2027')
  expect(await screen.findByRole('img', { name: 'Điện thoại VieTech' })).toHaveAttribute('src', 'https://images.test/phone.png')
  await describe()
  await userEvent.selectOptions(screen.getByLabelText('Loại lỗi'), 'Màn hình / hiển thị')
  await userEvent.click(screen.getByRole('checkbox', { name: 'Cáp sạc' }))
  const attachment = { FileUrl: 'https://storage.test/evidence.png', FileType: 'Image' }
  api.uploadWarrantyImage.mockResolvedValue(attachment)
  await userEvent.upload(screen.getByLabelText('Chọn ảnh minh chứng'), new File(['image'], 'loi.png', { type: 'image/png' }))
  await screen.findByText('Đã tải lên')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/tai-khoan'))
  expect(router.state.location.search).toBe('?section=service&request=request1')
  expect(api.createWarranty).toHaveBeenCalledWith('access-for-test', {
    OrderItemId: 'line1', ProductSerialId: 's2', IssueDescription: 'Loại lỗi: Màn hình / hiển thị\nMàn hình bị nhấp nháy khi sạc.\nPhụ kiện dự kiến gửi kèm: Cáp sạc', Attachments: [attachment],
  })
  expect(api.createWarranty).toHaveBeenCalledTimes(1)
})

test('requires an assigned device, nonblank issue and confirmation without posting invalid data', async () => {
  mount()
  await chooseProduct(null)
  expect(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' })).toBeDisabled()
  await userEvent.selectOptions(screen.getByLabelText('Serial / IMEI *'), 's1')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Vui lòng mô tả')
  await userEvent.type(screen.getByLabelText('Mô tả tình trạng lỗi *'), 'Lỗi nguồn')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Vui lòng xác nhận')
  expect(api.createWarranty).not.toHaveBeenCalled()
})

test('changing the order clears the old product and serial even if the same products are returned', async () => {
  mount()
  await chooseProduct()
  await userEvent.selectOptions(screen.getByLabelText('Mã đơn hàng *'), 'o2')
  await waitFor(() => expect(api.getWarrantyItems).toHaveBeenCalledWith('access-for-test', 'o2', expect.anything()))
  expect(screen.getByLabelText('Sản phẩm cần bảo hành *')).toHaveValue('')
  expect(screen.queryByLabelText('Serial / IMEI *')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' })).toBeDisabled()
})

test('supports nonserial accessories without inventing a serial', async () => {
  api.getWarrantyItems.mockResolvedValue([{ ...item, IsSerialTracked: false, Serials: [], WarrantyStartDate: '2026-10-01', WarrantyEndDate: '2027-09-30' }])
  mount()
  await chooseProduct(null)
  expect(screen.getByLabelText('Serial / IMEI')).toHaveValue('Sản phẩm không quản lý Serial/IMEI')
  await describe()
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' }))
  await waitFor(() => expect(api.createWarranty).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ ProductSerialId: null })))
})

test('ineligible devices show the server reason and cannot be submitted', async () => {
  api.getWarrantyItems.mockResolvedValue([{ ...item, CanRequest: false, Serials: [{ ...device('s1'), CanRequest: false, Reason: 'Đã hết hạn bảo hành.' }] }])
  mount()
  await chooseProduct(null)
  expect(await screen.findByText('Đã hết hạn bảo hành.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' })).toBeDisabled()
  expect(api.createWarranty).not.toHaveBeenCalled()
})

test('failed optional evidence blocks submission until retried or removed, and keeps the description', async () => {
  mount()
  await chooseProduct()
  await describe()
  api.uploadWarrantyImage.mockRejectedValueOnce(new Error('Không tải được ảnh.'))
  await userEvent.upload(screen.getByLabelText('Chọn ảnh minh chứng'), new File(['image'], 'anh.png', { type: 'image/png' }))
  await screen.findByText('Không tải được ảnh.')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' }))
  expect(api.createWarranty).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Mô tả tình trạng lỗi *')).toHaveValue('Màn hình bị nhấp nháy khi sạc.')
  await userEvent.click(screen.getByRole('button', { name: 'Xóa ảnh anh.png' }))
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' }))
  await waitFor(() => expect(api.createWarranty).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ Attachments: [] })))
})

test('guards repeated submission while a request is pending and preserves input after server failure', async () => {
  let reject
  api.createWarranty.mockReturnValue(new Promise((_, fail) => { reject = fail }))
  mount()
  await chooseProduct()
  await describe()
  const form = screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' }).closest('form')
  fireEvent.submit(form); fireEvent.submit(form)
  expect(api.createWarranty).toHaveBeenCalledTimes(1)
  await act(async () => reject(new Error('Máy chủ đang bận.')))
  expect(await screen.findByRole('alert')).toHaveTextContent('Máy chủ đang bận.')
  expect(screen.getByLabelText('Mô tả tình trạng lỗi *')).toHaveValue('Màn hình bị nhấp nháy khi sạc.')
  expect(screen.getByRole('button', { name: 'Gửi yêu cầu bảo hành' })).toBeEnabled()
})

test('shows actionable loading failure, retry and an empty delivered-order state', async () => {
  api.listMyOrders.mockRejectedValueOnce(new Error('Không đọc được đơn hàng.')).mockResolvedValueOnce({ Items: [], Total: 0 })
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Không đọc được đơn hàng.')
  await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText('Chưa có đơn hàng đã giao')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Xem lịch sử mua hàng' })).toHaveAttribute('href', '/tai-khoan?section=orders')
})
