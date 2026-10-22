import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { makeAuth } from '../../test/auth.js'
import ReturnCreatePage from './ReturnCreatePage.jsx'

const api = vi.hoisted(() => ({ listMyOrders: vi.fn(), getReturnItems: vi.fn(), createReturn: vi.fn(), uploadReturnImage: vi.fn(), getProduct: vi.fn() }))
vi.mock('../../lib/order-api.js', () => ({ listMyOrders: api.listMyOrders }))
vi.mock('../../lib/return-api.js', () => api)
vi.mock('../../lib/catalog-api.js', () => ({ getProduct: api.getProduct }))

const device = (id) => ({ ProductSerialId: id, SerialNumber: 'IMEI-' + id, CanRequest: true, Reason: null })
const item = { OrderItemId: 'line1', ProductId: 'product1', ProductVariantId: 'variant1', ProductName: 'Điện thoại VieTech', VariantInfo: 'Đen / 256GB', Quantity: 2,
  MaxQuantity: 1, IsSerialTracked: true, CanRequest: true, ReturnDeadline: '2026-10-27', WindowDays: 14, Serials: [device('s1'), device('s2')] }
const order = (id) => ({ OrderId: id, OrderCode: 'DH-' + id, OrderedAt: '2026-10-14T05:00:00Z', OrderStatus: 'Delivered' })

function mount() {
  const router = createMemoryRouter([{ path: '/new', element: <ReturnCreatePage /> }, { path: '/tai-khoan', element: <p>Danh sách đổi trả</p> }], { initialEntries: ['/new'] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Customer' })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}
async function chooseProduct(serial = 's2') {
  await screen.findByRole('option', { name: /DH-o1/ })
  await userEvent.selectOptions(screen.getByLabelText('Mã đơn hàng *'), 'o1')
  await screen.findByRole('option', { name: /Điện thoại VieTech/ })
  await userEvent.selectOptions(screen.getByLabelText('Sản phẩm đổi trả *'), 'line1')
  if (serial) await userEvent.selectOptions(screen.getByLabelText('Serial / IMEI *'), serial)
}
async function describe() {
  await userEvent.selectOptions(screen.getByLabelText('Lý do đổi trả *'), 'Sản phẩm bị lỗi')
  await userEvent.type(screen.getByLabelText('Mô tả chi tiết lý do đổi trả *'), 'Màn hình bị nhấp nháy khi mở máy.')
  await userEvent.click(screen.getByRole('checkbox', { name: /Tôi cam kết/ }))
}
beforeEach(() => {
  vi.resetAllMocks()
  api.listMyOrders.mockResolvedValue({ Items: [order('o1'), order('o2')], Total: 2 })
  api.getReturnItems.mockResolvedValue([item])
  api.createReturn.mockResolvedValue({ ReturnRequestId: 'request1', Status: 'Pending' })
  api.getProduct.mockResolvedValue({ Images: [{ ImageUrl: 'https://images.test/phone.png', SortOrder: 0 }], Variants: [] })
})

test('sends the selected return type, exact serial, quantity, public description and real uploaded attachment', async () => {
  const router = mount()
  await chooseProduct()
  expect(api.listMyOrders).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ order_status: ['Delivered', 'Completed'] }), expect.anything())
  expect(screen.getByText(/14 ngày tính từ ngày giao hàng/)).toHaveTextContent('27/10/2026')
  expect(screen.getByLabelText('Số lượng yêu cầu *')).toHaveAttribute('readonly')
  expect(await screen.findByRole('img', { name: 'Điện thoại VieTech' })).toHaveAttribute('src', 'https://images.test/phone.png')
  await describe()
  const attachment = { FileUrl: 'https://storage.test/return.png', FileType: 'Image' }
  api.uploadReturnImage.mockResolvedValue(attachment)
  await userEvent.upload(screen.getByLabelText('Chọn ảnh minh chứng'), new File(['image'], 'loi.png', { type: 'image/png' }))
  await screen.findByText('Đã tải lên')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }))
  await waitFor(() => expect(router.state.location.search).toBe('?section=service&type=return&request=request1'))
  expect(api.createReturn).toHaveBeenCalledWith('access-for-test', {
    OrderItemId: 'line1', ProductSerialId: 's2', Quantity: 1, RequestType: 'Exchange',
    Reason: 'Lý do: Sản phẩm bị lỗi\nMàn hình bị nhấp nháy khi mở máy.', Attachments: [attachment],
  })
  expect(api.createReturn).toHaveBeenCalledTimes(1)
})

test('uses exchange only without a return/exchange selector or unsupported bank fields', async () => {
  mount(); await chooseProduct(); await describe()
  expect(screen.queryByRole('radio')).not.toBeInTheDocument()
  expect(screen.getByText('Đổi sản phẩm mới')).toBeInTheDocument()
  expect(screen.queryByLabelText(/Số tài khoản/)).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }))
  await waitFor(() => expect(api.createReturn).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ RequestType: 'Exchange', Quantity: 1 })))
  expect(Object.keys(api.createReturn.mock.calls[0][1]).sort()).toEqual(['Attachments', 'OrderItemId', 'ProductSerialId', 'Quantity', 'Reason', 'RequestType'])
})

test('nonserial products also exchange exactly one unit', async () => {
  api.getReturnItems.mockResolvedValue([{ ...item, IsSerialTracked: false, MaxQuantity: 2, Quantity: 4, Serials: [] }])
  mount(); await chooseProduct(null); await describe()
  const input = screen.getByLabelText('Số lượng yêu cầu *')
  expect(input).toHaveAttribute('readonly')
  expect(input).toHaveValue(1)
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }))
  await waitFor(() => expect(api.createReturn).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ ProductSerialId: null, Quantity: 1 })))
})

test('requires a selected device, reason, detailed description and confirmation before posting', async () => {
  mount(); await chooseProduct(null)
  expect(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' })).toBeDisabled()
  await userEvent.selectOptions(screen.getByLabelText('Serial / IMEI *'), 's1')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Vui lòng chọn lý do')
  await userEvent.selectOptions(screen.getByLabelText('Lý do đổi trả *'), 'Lý do khác')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Vui lòng mô tả chi tiết')
  await userEvent.type(screen.getByLabelText('Mô tả chi tiết lý do đổi trả *'), 'Giao sai màu')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Vui lòng xác nhận')
  expect(api.createReturn).not.toHaveBeenCalled()
})

test('expiry or an open warranty displays the backend reason and blocks submission', async () => {
  api.getReturnItems.mockResolvedValue([{ ...item, CanRequest: false, Reason: 'Đã quá thời hạn đổi trả.', Serials: [{ ...device('s1'), CanRequest: false, Reason: 'Đã quá thời hạn đổi trả.' }] }])
  mount(); await chooseProduct(null)
  expect(await screen.findByText('Đã quá thời hạn đổi trả.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' })).toBeDisabled()
})

test('changing an order resets the selected item, serial and quantity', async () => {
  mount(); await chooseProduct()
  await userEvent.selectOptions(screen.getByLabelText('Mã đơn hàng *'), 'o2')
  await waitFor(() => expect(api.getReturnItems).toHaveBeenCalledWith('access-for-test', 'o2', expect.anything()))
  expect(screen.getByLabelText('Sản phẩm đổi trả *')).toHaveValue('')
  expect(screen.queryByLabelText('Serial / IMEI *')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' })).toBeDisabled()
})

test('failed evidence blocks sending until removed and preserves customer input', async () => {
  mount(); await chooseProduct(); await describe()
  api.uploadReturnImage.mockRejectedValueOnce(new Error('Không tải được ảnh.'))
  await userEvent.upload(screen.getByLabelText('Chọn ảnh minh chứng'), new File(['image'], 'anh.png', { type: 'image/png' }))
  await screen.findByText('Không tải được ảnh.')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }))
  expect(api.createReturn).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Xóa ảnh anh.png' }))
  await userEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }))
  await waitFor(() => expect(api.createReturn).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ Attachments: [], Reason: expect.stringContaining('Màn hình bị nhấp nháy') })))
})

test('prevents repeated posts and refreshes eligibility after a concurrent quantity conflict without losing the form', async () => {
  let reject
  api.createReturn.mockReturnValue(new Promise((_, fail) => { reject = fail }))
  mount(); await chooseProduct(); await describe()
  const form = screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }).closest('form')
  fireEvent.submit(form); fireEvent.submit(form)
  expect(api.createReturn).toHaveBeenCalledTimes(1)
  await act(async () => reject(Object.assign(new Error('Sản phẩm vừa có yêu cầu khác.'), { code: 'return_request_open' })))
  expect(await screen.findByRole('alert')).toHaveTextContent('Sản phẩm vừa có yêu cầu khác.')
  await waitFor(() => expect(api.getReturnItems).toHaveBeenCalledTimes(2))
  expect(screen.getByLabelText('Mô tả chi tiết lý do đổi trả *')).toHaveValue('Màn hình bị nhấp nháy khi mở máy.')
})

test('an unavailable order list can be retried and an empty list points to order history', async () => {
  api.listMyOrders.mockRejectedValueOnce(new Error('Không tải được đơn hàng.')).mockResolvedValueOnce({ Items: [], Total: 0 })
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Không tải được đơn hàng.')
  await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText('Chưa có đơn hàng đã giao')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Xem lịch sử mua hàng' })).toHaveAttribute('href', '/tai-khoan?section=orders')
})

test('out-of-stock credit notice sits immediately above and outside the confirmation footer', async () => {
  api.getReturnItems.mockResolvedValue([{ ...item, OriginalInStock: false, ExchangeCreditLimit: '12000000' }])
  mount(); await chooseProduct()
  const notice = screen.getByText(/Bạn được dùng giá trị 12.000.000đ/)
  const footer = screen.getByRole('button', { name: 'Gửi yêu cầu đổi trả' }).closest('.cw-confirm')
  expect(footer.previousElementSibling).toBe(notice)
  expect(footer).not.toContainElement(notice)
})

test('in-stock original shows no red exchange-credit notice', async () => {
  api.getReturnItems.mockResolvedValue([{ ...item, OriginalInStock: true, ExchangeCreditLimit: '12000000' }])
  mount(); await chooseProduct()
  expect(screen.queryByText(/Bạn được dùng giá trị/)).not.toBeInTheDocument()
})
