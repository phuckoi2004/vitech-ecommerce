import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { AuthContext } from '../../../auth/context.js'
import { formatMoney } from '../../../lib/format.js'
import { makeAuth } from '../../../test/auth.js'
import OrderHistory from './OrderHistory.jsx'

const api = vi.hoisted(() => ({ listMyOrders: vi.fn() }))
vi.mock('../../../lib/order-api.js', () => api)

// Text as the default Testing Library normalizer sees it (Intl puts a no-break space before "₫").
const vnd = (value) => formatMoney(value).replace(/\s/g, ' ')

const line = (ProductName, ProductSlug, extra = {}) => ({ OrderItemId: `${ProductSlug}-line`, ProductName, VariantInfo: '256GB', Quantity: 1, ProductSlug, ...extra })
const SHIPPING = {
  OrderId: 'o1', OrderCode: 'VT261004AAAAAA', TotalAmount: '41990000.00', OrderStatus: 'Shipping', PaymentStatus: 'Paid',
  OrderedAt: '2026-10-04T03:00:00Z', Items: [line('iPhone 18 Pro Max 256GB', 'iphone-18-pro-max')],
}
const DELIVERED = {
  OrderId: 'o2', OrderCode: 'VT260922BBBBBB', TotalAmount: '31490000.00', OrderStatus: 'Delivered', PaymentStatus: 'Paid',
  OrderedAt: '2026-09-22T03:00:00Z', Items: [line('Samsung Galaxy S26 Ultra', 'galaxy-s26-ultra'), line('Ốp lưng S26', 'op-lung-s26')],
}
const page = (Items, Total = Items.length) => ({ Items, Total, Page: 1, PageSize: 10 })

function renderAt(url) {
  const router = createMemoryRouter([
    { path: '/tai-khoan', element: <OrderHistory /> },
    { path: '/don-hang/:orderId', element: <p>Trang đơn hàng</p> },
    { path: '/san-pham/:slug', element: <p>Trang sản phẩm</p> },
    { path: '/', element: <p>Trang chủ</p> },
  ], { initialEntries: [url] })
  render(<AuthContext.Provider value={makeAuth({ role: 'Customer' })}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

const lastQuery = () => api.listMyOrders.mock.calls.at(-1)[1]

afterEach(() => vi.clearAllMocks())

describe('order history', () => {
  test('lists the orders as designed: code and date, products, total, status and the actions each allows', async () => {
    api.listMyOrders.mockResolvedValue(page([SHIPPING, DELIVERED]))
    const router = renderAt('/tai-khoan?section=orders')

    const cards = await screen.findAllByRole('listitem')
    expect(api.listMyOrders).toHaveBeenCalledWith('access-for-test', expect.objectContaining({ order_status: [], page: 1, page_size: 10 }), expect.anything())
    expect(within(cards[0]).getByText('VT261004AAAAAA • 04/10/2026')).toBeInTheDocument()
    expect(within(cards[0]).getByText('iPhone 18 Pro Max 256GB')).toBeInTheDocument()
    expect(within(cards[0]).getByText(vnd('41990000.00'))).toBeInTheDocument()
    expect(within(cards[0]).getByText('Đang vận chuyển')).toBeInTheDocument()
    expect(within(cards[0]).queryByText('Đánh giá sản phẩm')).not.toBeInTheDocument()
    expect(within(cards[1]).getByText('Samsung Galaxy S26 Ultra và 1 sản phẩm khác')).toBeInTheDocument()

    // A delivered order with two products lets the customer pick which one to review.
    await userEvent.click(within(cards[1]).getByText('Đánh giá sản phẩm'))
    expect(within(cards[1]).getByRole('link', { name: 'Ốp lưng S26' })).toHaveAttribute('href', '/san-pham/op-lung-s26?review=o2#product-reviews')

    await userEvent.click(within(cards[0]).getByRole('link', { name: 'Xem chi tiết đơn VT261004AAAAAA' }))
    expect(router.state.location.pathname).toBe('/don-hang/o1')
  })

  test('tabs, code and dates go to the URL and ask the API for the statuses and whole days chosen', async () => {
    api.listMyOrders.mockResolvedValue(page([SHIPPING]))
    const router = renderAt('/tai-khoan?section=orders&page=2')
    await screen.findByText('VT261004AAAAAA • 04/10/2026')

    await userEvent.click(screen.getByRole('button', { name: 'Đã nhận hàng' }))
    expect(screen.getByRole('button', { name: 'Đã nhận hàng' })).toHaveAttribute('aria-pressed', 'true')
    expect(router.state.location.search).toBe('?section=orders&status=received')
    expect(lastQuery()).toMatchObject({ order_status: ['Delivered', 'Completed'], page: 1 })

    await userEvent.type(screen.getByLabelText('Tìm theo mã đơn'), ' VT2610 ')
    await userEvent.type(screen.getByLabelText('Từ ngày'), '2026-10-01')
    await userEvent.type(screen.getByLabelText('Đến ngày'), '2026-10-04')
    await userEvent.click(screen.getByRole('button', { name: 'Tìm kiếm' }))
    expect(lastQuery()).toMatchObject({
      order_status: ['Delivered', 'Completed'], order_code: 'VT2610',
      ordered_from: '2026-10-01T00:00:00+07:00', ordered_to: '2026-10-05T00:00:00+07:00',
    })
    expect(new URLSearchParams(router.state.location.search).get('code')).toBe('VT2610')
  })

  test('a start day after the end day is refused without asking the API', async () => {
    api.listMyOrders.mockResolvedValue(page([SHIPPING]))
    renderAt('/tai-khoan?section=orders')
    await screen.findByText('VT261004AAAAAA • 04/10/2026')
    const calls = api.listMyOrders.mock.calls.length

    await userEvent.type(screen.getByLabelText('Từ ngày'), '2026-10-04')
    await userEvent.type(screen.getByLabelText('Đến ngày'), '2026-10-01')
    await userEvent.click(screen.getByRole('button', { name: 'Tìm kiếm' }))
    expect(screen.getByRole('alert')).toHaveTextContent('"Từ ngày" không được sau "Đến ngày".')
    expect(api.listMyOrders).toHaveBeenCalledTimes(calls)
  })

  test('says when there are no orders yet, when filters match none, and lets a failed load be retried', async () => {
    api.listMyOrders.mockResolvedValueOnce(page([]))
    renderAt('/tai-khoan?section=orders')
    expect(await screen.findByRole('heading', { name: 'Bạn chưa có đơn hàng nào' })).toBeInTheDocument()

    api.listMyOrders.mockResolvedValueOnce(page([]))
    await userEvent.click(screen.getByRole('button', { name: 'Đã hủy' }))
    expect(await screen.findByRole('heading', { name: 'Không tìm thấy đơn hàng phù hợp' })).toBeInTheDocument()

    api.listMyOrders.mockRejectedValueOnce(new Error('Không thể kết nối máy chủ.'))
    api.listMyOrders.mockResolvedValueOnce(page([SHIPPING]))
    await userEvent.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Không thể kết nối máy chủ.')
    await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('VT261004AAAAAA • 04/10/2026')).toBeInTheDocument()
  })
})
