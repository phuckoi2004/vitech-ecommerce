import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { AuthApiError } from '../../lib/auth-api.js'
import { formatMoney } from '../../lib/format.js'
import { appRoutes } from '../../routes.jsx'
import { makeAuth } from '../../test/auth.js'
import { orderTotal } from '../components/cart/cartLines.js'
import { normalizePhone, orderPayload, shippingDetail, validateCheckout } from '../components/checkout/checkoutForm.js'

// Text as the default Testing Library normalizer sees it (Intl puts a no-break space before "₫").
const vnd = (value) => formatMoney(value).replace(/\s/g, ' ')

const LINES = [
  { CartItemId: 'ci1', ProductVariantId: 'v1', ProductId: 'p1', ProductName: 'iPhone 18 Pro Max', VariantName: '256GB Đỏ', Sku: 'A',
    Quantity: 2, UnitPrice: '41990000.00', CurrentPrice: '41990000.00', LineTotal: '83980000.00', IsSelected: true,
    IsAvailable: true, StockQuantity: 5, AddedAt: '2026-10-13T00:00:00Z' },
  { CartItemId: 'ci2', ProductVariantId: 'v9', ProductId: 'p9', ProductName: 'Tai nghe chưa chọn', VariantName: 'Trắng', Sku: 'B',
    Quantity: 1, UnitPrice: '990000.00', CurrentPrice: '990000.00', LineTotal: '990000.00', IsSelected: false,
    IsAvailable: true, StockQuantity: 5, AddedAt: '2026-10-13T00:00:00Z' },
]
const cartOf = (items) => ({
  CartId: 'cart1', CreatedAt: '2026-10-13T00:00:00Z', UpdatedAt: '2026-10-13T00:00:00Z', Items: items,
  SelectedQuantity: items.filter((i) => i.IsSelected && i.IsAvailable).reduce((sum, i) => sum + i.Quantity, 0),
  SelectedSubtotal: items.filter((i) => i.IsSelected && i.IsAvailable).reduce((sum, i) => sum + Number(i.LineTotal), 0).toFixed(2),
})
const PRODUCT = {
  ProductId: 'p1', Name: 'iPhone 18 Pro Max', Slug: 'iphone-18', Status: 'Active',
  Images: [{ ProductImageId: 'i1', ImageUrl: 'https://cdn.test/p1.png', DisplayOrder: 0, IsDefault: true }],
  Variants: [{ ProductVariantId: 'v1', Color: 'Đỏ', Storage: '256GB', Price: '41990000.00', StockQuantity: 5 }],
}
const ADDRESSES = [
  { AddressId: 'a1', UserId: 'u', ReceiverName: 'Trần Thị C', ReceiverPhone: '0901111222', Province: 'Hà Nội', Ward: 'Phường Cầu Giấy',
    DetailAddress: '5 Xuân Thủy', IsDefault: false },
  { AddressId: 'a2', UserId: 'u', ReceiverName: 'Nguyễn Văn B', ReceiverPhone: '0987654321', Province: 'TP Hồ Chí Minh',
    Ward: 'Phường Bến Nghé', DetailAddress: '12 Lê Lợi', IsDefault: true },
]
const SHIPPING = [
  { ShippingMethodId: 's1', Code: 'STD', Name: 'Giao hàng tiêu chuẩn', BaseFee: '30000.00', EstimatedDays: 3, IsActive: true },
  { ShippingMethodId: 's2', Code: 'FAST', Name: 'Giao hàng nhanh', BaseFee: '50000.00', EstimatedDays: 1, IsActive: true },
]
const PAYMENT = [
  { PaymentMethodId: 'm2', Code: 'QR', Name: 'Chuyển khoản QR', Description: 'Quét mã QR sau khi đặt hàng.', IsActive: true, DisplayOrder: 2 },
  { PaymentMethodId: 'm1', Code: 'COD', Name: 'Thanh toán khi nhận hàng (COD)', Description: 'Trả tiền mặt khi nhận hàng.', IsActive: true, DisplayOrder: 1 },
]

// The order the server returns: its total differs from the page's estimate, so what is shown afterwards is the server's.
const ORDER = {
  OrderId: 'o1', OrderCode: 'VT261016ABC123', TotalAmount: '83500000.00', OrderStatus: 'Pending', PaymentStatus: 'Pending',
  OrderedAt: '2026-10-16T03:00:00Z', AddressId: 'a2', ShippingMethodId: 's1', PaymentMethodId: 'm1', CouponId: null,
  Subtotal: '83980000.00', ShippingFee: '30000.00', DiscountAmount: '510000.00', ReceiverName: 'Nguyễn Văn B',
  ReceiverPhone: '0987654321', ShippingAddress: '12 Lê Lợi, Phường Bến Nghé, TP Hồ Chí Minh', CustomerNote: null,
  CancelReason: null, ConfirmedAt: null, ShippedAt: null, DeliveredAt: null, CompletedAt: null, CancelledAt: null,
  Items: [], StatusHistories: [],
}

// API of the page. `overrides['METHOD /endpoint']` or `overrides['/endpoint']` (any method) replaces a response
// ({status, body}, or {network: true} for a failed connection), or is a function of the call count and the call
// returning one, or a promise of one.
function mockApi(overrides = {}) {
  const calls = []
  const counts = {}
  let created = null // the order placed by POST /orders, read again by the order page
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost')
    const endpoint = url.pathname.replace(/^\/api/, '')
    const method = options.method ?? 'GET'
    const call = { endpoint, method, query: Object.fromEntries(url.searchParams), token: options.headers?.Authorization,
      body: options.body === undefined ? undefined : JSON.parse(options.body) }
    calls.push(call)
    const key = `${method} ${endpoint}` in overrides ? `${method} ${endpoint}` : endpoint
    counts[key] = (counts[key] ?? 0) + 1
    const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
    const override = await (typeof overrides[key] === 'function' ? overrides[key](counts[key], call) : overrides[key])
    if (override?.network) throw new TypeError('Failed to fetch')
    if (override) return reply(override.status ?? 200, override.body)
    if (endpoint === '/cart') return reply(200, cartOf(LINES))
    if (endpoint === '/users/me/addresses') return reply(200, ADDRESSES)
    if (endpoint === '/shipping-methods') return reply(200, SHIPPING)
    if (endpoint === '/payment-methods') return reply(200, PAYMENT)
    if (endpoint === '/products/p1') return reply(200, PRODUCT)
    if (endpoint === '/users/me/notifications/unread-count') return reply(200, { Count: 0 })
    if (endpoint === '/orders' && method === 'POST') {
      created = { ...ORDER, PaymentMethodId: call.body.PaymentMethodId }
      return reply(201, created)
    }
    if (endpoint === '/orders') return reply(200, { Items: [ORDER], Total: 1, Page: 1, PageSize: 1 })
    if (endpoint === '/orders/o1') return reply(200, created ?? ORDER)
    if (endpoint === '/orders/o1/payments/qr' && method === 'POST') {
      return reply(201, { PaymentTransactionId: 't1', OrderId: 'o1', PaymentMethodId: 'm2', TransactionType: 'Payment',
        Amount: ORDER.TotalAmount, Status: 'Pending', QrData: 'https://qr.example/img', PaidAt: null, CreatedAt: ORDER.OrderedAt,
        RefundOfPaymentTransactionId: null, TransferContent: 'VTPAY12345678', Bank: 'Vietcombank', AccountNumber: '0123456789',
        TransferAmount: 83500000, ExpiresAt: '2099-01-01T00:00:00Z' })
    }
    return reply(404, { detail: 'Không tìm thấy' })
  }))
  return {
    calls,
    writes: () => calls.filter((call) => call.method !== 'GET'),
    posts: () => calls.filter((call) => call.endpoint === '/orders' && call.method === 'POST'),
    reads: (endpoint) => calls.filter((call) => call.endpoint === endpoint && call.method === 'GET').length,
  }
}

function renderAt(url, auth = makeAuth({ role: 'Customer' })) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [url] })
  render(<AuthContext.Provider value={auth}><RouterProvider router={router} /></AuthContext.Provider>)
  return router
}

const summary = () => screen.getByRole('complementary', { name: 'Đơn hàng của bạn' })

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('checkout form rules', () => {
  test('phone numbers follow the backend rule for Vietnamese numbers', () => {
    expect(normalizePhone('0912 345 678')).toBe('0912345678')
    expect(normalizePhone('+84 912-345-678')).toBe('0912345678')
    expect(normalizePhone('0084912345678')).toBe('0912345678')
    expect(normalizePhone('02438123456')).toBe('02438123456')
    expect(normalizePhone('0123456789')).toBeNull()
    expect(normalizePhone('09123')).toBeNull()
  })

  test('validation names every missing choice and the order body carries no price', () => {
    const empty = { ReceiverName: ' ', ReceiverPhone: '', Province: '', Ward: '', DetailAddress: '' }
    expect(Object.keys(validateCheckout({ delivery: { mode: 'new', receiver: empty }, shippingMethodId: null, paymentMethodId: null })))
      .toEqual(['ReceiverName', 'ReceiverPhone', 'Province', 'Ward', 'DetailAddress', 'shipping', 'payment'])
    expect(validateCheckout({ delivery: { mode: 'saved', addressId: null }, shippingMethodId: 's1', paymentMethodId: 'm1' }))
      .toEqual({ address: 'Vui lòng chọn địa chỉ nhận hàng.' })

    expect(orderPayload({ delivery: { mode: 'saved', addressId: 'a2' }, shippingMethodId: 's1', paymentMethodId: 'm1', note: '  ' }))
      .toEqual({ ShippingMethodId: 's1', PaymentMethodId: 'm1', AddressId: 'a2' })
    const receiver = { ReceiverName: ' Lê D ', ReceiverPhone: '+84 912 345 678', Province: 'Đà Nẵng', Ward: 'Phường Hải Châu', DetailAddress: '1 Bạch Đằng ' }
    expect(orderPayload({ delivery: { mode: 'new', receiver }, shippingMethodId: 's2', paymentMethodId: 'm2', note: ' Gọi trước ' })).toEqual({
      ShippingMethodId: 's2', PaymentMethodId: 'm2', ReceiverName: 'Lê D', ReceiverPhone: '0912345678',
      ShippingAddress: '1 Bạch Đằng, Phường Hải Châu, Đà Nẵng', CustomerNote: 'Gọi trước',
    })
    expect(shippingDetail({ BaseFee: '0.00', EstimatedDays: 3 })).toBe('Dự kiến 3 ngày • Miễn phí')
  })

  test('the total follows the order API (subtotal − discount + shipping fee) and the body carries only the code', () => {
    // Same figures as backend/tests/api/test_promotion_api.py test_success_preview_and_checkout_with_coupon.
    expect(orderTotal({ subtotal: '200000.00', discount: '20000.00', shippingFee: '30000.00' })).toBe(210000)
    expect(orderTotal({ subtotal: '83980000.00', shippingFee: '0.00' })).toBe(83980000)
    expect(orderTotal({ subtotal: '0.10', shippingFee: '0.20' })).toBe(0.3)
    const form = { delivery: { mode: 'saved', addressId: 'a2' }, shippingMethodId: 's1', paymentMethodId: 'm1' }
    expect(orderPayload({ ...form, couponCode: 'GIAM10' }))
      .toEqual({ ShippingMethodId: 's1', PaymentMethodId: 'm1', AddressId: 'a2', CouponCode: 'GIAM10' })
    expect(orderPayload({ ...form, couponCode: '' })).not.toHaveProperty('CouponCode')
  })
})

describe('checkout page', () => {
  test('"Mua hàng" opens the confirmation page with the selected lines read again from the cart API', async () => {
    const server = mockApi({ '/cart': { body: cartOf(LINES) } })
    const user = userEvent.setup()
    const router = renderAt('/gio-hang')

    await user.click(await screen.findByRole('link', { name: 'Mua hàng' }))
    expect(router.state.location.pathname).toBe('/dat-hang')
    expect(await screen.findByRole('heading', { level: 1, name: 'Xác nhận đặt hàng' })).toBeInTheDocument()

    const item = await within(summary()).findByRole('article', { name: 'iPhone 18 Pro Max' })
    expect(within(summary()).queryByRole('article', { name: 'Tai nghe chưa chọn' })).not.toBeInTheDocument()
    await waitFor(() => expect(item.querySelector('img')).toHaveAttribute('src', 'https://cdn.test/p1.png'))
    expect(within(item).getByText('Đỏ • 256GB • SL: 2')).toBeInTheDocument()
    expect(within(item).getByText(vnd(41990000))).toBeInTheDocument()
    expect(within(item).getByText(vnd(83980000))).toBeInTheDocument()
    expect(within(summary()).getByText('Tạm tính (2 sản phẩm)').nextElementSibling).toHaveTextContent(vnd(83980000))
    expect(await within(summary()).findByText('Phí vận chuyển')).toBeInTheDocument()
    await waitFor(() => expect(within(summary()).getByText('Phí vận chuyển').nextElementSibling).toHaveTextContent(vnd(30000)))
    expect(within(summary()).getByText(vnd(84010000))).toBeInTheDocument()
    // Read by the cart page, again by this page, and once by the header cart entry (CartLink) kept across both.
    expect(server.calls.filter((call) => call.endpoint === '/cart')).toHaveLength(3)
    expect(server.calls.find((call) => call.endpoint === '/users/me/addresses').token).toBe('Bearer access-for-test')

    // Customer information comes from the signed-in account; the default address is chosen.
    const customer = screen.getByRole('region', { name: /Thông tin khách hàng/ })
    expect(within(customer).getByText('Customer for test')).toBeInTheDocument()
    expect(within(customer).getByText('0912345678')).toBeInTheDocument()
    expect(within(customer).getByText('customer@example.com')).toBeInTheDocument()
    expect(await screen.findByText('Nguyễn Văn B • 0987654321')).toBeInTheDocument()
    expect(screen.getByText('12 Lê Lợi, Phường Bến Nghé, TP Hồ Chí Minh')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Quay lại giỏ hàng' })).toHaveAttribute('href', '/gio-hang')
    expect(document.title).toBe('Xác nhận đặt hàng | VieTech')
  })

  test('shipping and payment methods come from the API; the chosen fee changes the total', async () => {
    mockApi()
    const user = userEvent.setup()
    renderAt('/dat-hang')

    const standard = await screen.findByRole('radio', { name: /Giao hàng tiêu chuẩn/ })
    expect(standard).toBeChecked()
    expect(screen.getByText(`Dự kiến 3 ngày • ${vnd(30000)}`)).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: /Giao hàng nhanh/ }))
    expect(within(summary()).getByText('Phí vận chuyển').nextElementSibling).toHaveTextContent(vnd(50000))
    expect(within(summary()).getByText(vnd(84030000))).toBeInTheDocument()

    const payments = screen.getAllByRole('radio').filter((radio) => radio.name === 'checkout-payment')
    expect(payments.map((radio) => radio.closest('label').textContent)).toEqual([
      'Thanh toán khi nhận hàng (COD)Trả tiền mặt khi nhận hàng.', 'Chuyển khoản QRQuét mã QR sau khi đặt hàng.'])
    expect(payments[0]).toBeChecked()
  })

  test('another saved address or a new receiver can be chosen; a new receiver is checked before the order is sent', async () => {
    const server = mockApi()
    const user = userEvent.setup()
    const router = renderAt('/dat-hang')

    await user.click(await screen.findByRole('button', { name: 'Thay đổi' }))
    await user.click(screen.getByRole('radio', { name: /Trần Thị C/ }))
    expect(screen.getByText('5 Xuân Thủy, Phường Cầu Giấy, Hà Nội')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Thay đổi' }))
    await user.click(screen.getByRole('radio', { name: /Giao đến địa chỉ khác/ }))
    const name = screen.getByRole('textbox', { name: 'Họ và tên người nhận' })
    expect(name).toHaveValue('Customer for test')
    expect(screen.getByRole('textbox', { name: 'Số điện thoại' })).toHaveValue('0912345678')
    await user.clear(name)
    await user.clear(screen.getByRole('textbox', { name: 'Số điện thoại' }))
    await user.type(screen.getByRole('textbox', { name: 'Số điện thoại' }), '12345')
    await user.click(screen.getByRole('button', { name: 'Xác nhận đặt hàng' }))

    expect(name).toHaveFocus()
    expect(name).toHaveAttribute('aria-invalid', 'true')
    expect(name).toHaveAccessibleDescription('Vui lòng nhập họ tên người nhận.')
    expect(screen.getByText('Số điện thoại không hợp lệ. Vui lòng nhập số Việt Nam, ví dụ 0912345678.')).toBeInTheDocument()
    expect(screen.getByText('Vui lòng nhập Tỉnh/Thành phố.')).toBeInTheDocument()
    expect(screen.getByText('Vui lòng nhập Phường/Xã.')).toBeInTheDocument()
    expect(screen.getByText('Vui lòng nhập địa chỉ chi tiết (số nhà, tên đường).')).toBeInTheDocument()
    // An invalid form sends nothing.
    expect(server.writes()).toEqual([])

    // Pasted rather than typed key by key: each keystroke re-renders the whole page with its header.
    async function fill(label, value) {
      const input = screen.getByRole('textbox', { name: label })
      await user.clear(input)
      await user.click(input)
      await user.paste(value)
    }
    await fill('Họ và tên người nhận', 'Lê Văn D')
    await fill('Số điện thoại', '+84 912 345 678')
    await fill('Tỉnh/Thành phố', 'Đà Nẵng')
    await fill('Phường/Xã', 'Phường Hải Châu')
    await fill('Địa chỉ chi tiết', '1 Bạch Đằng')
    await fill('Ghi chú đơn hàng', 'Gọi trước khi giao')
    expect(screen.queryByText('Vui lòng nhập Tỉnh/Thành phố.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Xác nhận đặt hàng' }))

    // One order with the receiver typed here; nothing is saved to the address book and no payment is started.
    await waitFor(() => expect(router.state.location.pathname).toBe('/don-hang/o1'))
    expect(server.writes()).toEqual([expect.objectContaining({ endpoint: '/orders', method: 'POST', token: 'Bearer access-for-test', body: {
      ShippingMethodId: 's1', PaymentMethodId: 'm1', ReceiverName: 'Lê Văn D', ReceiverPhone: '0912345678',
      ShippingAddress: '1 Bạch Đằng, Phường Hải Châu, Đà Nẵng', CustomerNote: 'Gọi trước khi giao',
    } })])
  })

  test('without saved addresses the receiver form is shown at once; a failed address book can be retried', async () => {
    mockApi({ '/users/me/addresses': (count) => count === 1 ? { status: 500, body: { detail: 'Lỗi' } } : { body: [] } })
    const user = userEvent.setup()
    renderAt('/dat-hang')

    expect(await screen.findByText(/Không tải được sổ địa chỉ/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Họ và tên người nhận' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Thay đổi' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Thử lại' }))
    await waitFor(() => expect(screen.queryByText(/Không tải được sổ địa chỉ/)).not.toBeInTheDocument())
    expect(screen.getByRole('textbox', { name: 'Tỉnh/Thành phố' })).toBeInTheDocument()
  })

  test('no shipping or payment method blocks the order with a clear message', async () => {
    mockApi({ '/shipping-methods': { body: [] }, '/payment-methods': { status: 503, body: { detail: 'Service Unavailable' } } })
    const user = userEvent.setup()
    renderAt('/dat-hang')

    expect(await screen.findByText('Hiện chưa có phương thức vận chuyển khả dụng.')).toBeInTheDocument()
    expect(await screen.findByText('Hệ thống đang bận. Vui lòng thử lại sau.')).toBeInTheDocument()
    expect(within(summary()).getByText('Chọn phương thức vận chuyển')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Xác nhận đặt hàng' }))
    expect(screen.getByText('Vui lòng chọn phương thức vận chuyển.')).toBeInTheDocument()
    expect(screen.getByText('Vui lòng chọn phương thức thanh toán.')).toBeInTheDocument()
  })

  test.each([
    ['nothing is selected', cartOf(LINES.map((line) => ({ ...line, IsSelected: false }))), 'Chưa có sản phẩm nào được chọn', /chọn sản phẩm bạn muốn mua/],
    ['a selected line cannot be bought', cartOf([{ ...LINES[0], IsAvailable: false, StockQuantity: 1 }]), 'Chưa thể đặt hàng', /không thể mua/],
  ])('the page sends the customer back to the cart when %s', async (_, cart, title, description) => {
    mockApi({ '/cart': { body: cart } })
    renderAt('/dat-hang')

    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.getByText(description)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Quay lại giỏ hàng' })).toHaveAttribute('href', '/gio-hang')
    expect(screen.queryByRole('button', { name: 'Xác nhận đặt hàng' })).not.toBeInTheDocument()
  })

  test('a failed cart load can be retried', async () => {
    // Down until the retry (the header cart entry reads the same endpoint, so no call count is used).
    let down = true
    mockApi({ '/cart': () => down ? { status: 500, body: { detail: 'Lỗi' } } : { body: cartOf(LINES) } })
    const user = userEvent.setup()
    renderAt('/dat-hang')

    expect(await screen.findByRole('heading', { name: 'Không thể tải đơn hàng' })).toBeInTheDocument()
    down = false
    await user.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await within(await screen.findByRole('complementary', { name: 'Đơn hàng của bạn' }))
      .findByRole('article', { name: 'iPhone 18 Pro Max' })).toBeInTheDocument()
  })

  test('guests sign in first and come back to the confirmation page', async () => {
    const server = mockApi()
    const router = renderAt('/dat-hang', makeAuth())
    await waitFor(() => expect(router.state.location.pathname).toBe('/dang-nhap'))
    expect(router.state.location.search).toBe('?next=%2Fdat-hang')
    expect(server.calls.some((call) => call.endpoint === '/cart')).toBe(false)
  })
})

describe('coupon on the confirmation page', () => {
  const COUPON_KEY = 'vietech-cart-coupon:Customer-id'
  const previewOf = (subtotal, discount, code = 'GIAM10') => ({
    body: { Code: code, PromotionId: 'promo1', Subtotal: subtotal, EligibleSubtotal: subtotal, DiscountAmount: discount },
  })
  const previews = (server) => server.calls.filter((call) => call.endpoint === '/cart/coupon-preview')
  const row = (label) => within(summary()).getByText(label).nextElementSibling
  const confirm = () => screen.getByRole('button', { name: 'Xác nhận đặt hàng' })

  test('the code applied in the cart is checked again here and the total is subtotal − discount + shipping fee', async () => {
    sessionStorage.setItem(COUPON_KEY, 'GIAM10')
    const server = mockApi({ '/cart/coupon-preview': previewOf('83980000.00', '500000.00') })
    const user = userEvent.setup()
    renderAt('/gio-hang')

    await user.click(await screen.findByRole('link', { name: 'Mua hàng' }))
    expect(await within(await screen.findByRole('complementary', { name: 'Đơn hàng của bạn' })).findByText('GIAM10')).toBeInTheDocument()
    await waitFor(() => expect(row('Giảm giá')).toHaveTextContent(`−${vnd(500000)}`))
    await waitFor(() => expect(row('Phí vận chuyển')).toHaveTextContent(vnd(30000)))
    expect(within(summary()).getByText(vnd(83510000))).toBeInTheDocument()
    expect(previews(server)).toHaveLength(2) // once in the cart, once again on entering this page
    expect(previews(server)[1]).toMatchObject({ query: { code: 'GIAM10' }, token: 'Bearer access-for-test' })

    // The shipping fee does not take part in the discount: no new check.
    await user.click(screen.getByRole('radio', { name: /Giao hàng nhanh/ }))
    expect(within(summary()).getByText(vnd(83530000))).toBeInTheDocument()
    expect(previews(server)).toHaveLength(2)
    expect(confirm()).toBeEnabled()
    expect(server.writes()).toEqual([])
  })

  test('without a code the summary says "Chưa áp dụng", has no discount line and asks nothing', async () => {
    const server = mockApi()
    renderAt('/dat-hang')

    await within(await screen.findByRole('complementary', { name: 'Đơn hàng của bạn' })).findByText('iPhone 18 Pro Max')
    expect(row('Mã giảm giá')).toHaveTextContent('Chưa áp dụng')
    expect(within(summary()).queryByText('Giảm giá')).not.toBeInTheDocument()
    expect(previews(server)).toHaveLength(0)
  })

  test('a rejected code blocks the order with the server message until it is removed, also for the cart', async () => {
    sessionStorage.setItem(COUPON_KEY, 'HETHAN')
    const server = mockApi({ '/cart/coupon-preview': { status: 400, body: { detail: 'Mã giảm giá không còn hiệu lực', code: 'coupon_expired' } } })
    const user = userEvent.setup()
    renderAt('/dat-hang')

    expect(await within(await screen.findByRole('complementary', { name: 'Đơn hàng của bạn' })).findByRole('alert'))
      .toHaveTextContent('Mã giảm giá không còn hiệu lực')
    expect(within(summary()).queryByText('Giảm giá')).not.toBeInTheDocument()
    await waitFor(() => expect(within(summary()).getByText(vnd(84010000))).toBeInTheDocument())
    expect(confirm()).toBeDisabled()
    expect(confirm()).toHaveAccessibleDescription('Mã giảm giá HETHAN không dùng được. Hãy bỏ mã hoặc quay lại giỏ hàng để đổi mã.')

    await user.click(within(summary()).getByRole('button', { name: 'Bỏ mã' }))
    expect(row('Mã giảm giá')).toHaveTextContent('Chưa áp dụng')
    expect(confirm()).toBeEnabled()
    expect(sessionStorage.getItem(COUPON_KEY)).toBeNull()

    await user.click(screen.getByRole('link', { name: 'Quay lại giỏ hàng' }))
    expect(await screen.findByText('Áp dụng mã giảm giá')).toBeInTheDocument()
    expect(previews(server)).toHaveLength(1)
  })

  test.each([
    ['a 503', { status: 503, body: { detail: 'Service Unavailable' } }, 'Hệ thống đang bận. Vui lòng thử lại sau.'],
    ['a lost connection', { network: true }, 'Không kết nối được máy chủ. Vui lòng kiểm tra kết nối và thử lại.'],
  ])('after %s the code is not called invalid: the order waits for "Thử lại" or goes on after "Bỏ mã"', async (_, failure, message) => {
    sessionStorage.setItem(COUPON_KEY, 'GIAM10')
    mockApi({ '/cart/coupon-preview': (count) => count === 1 ? failure : previewOf('83980000.00', '500000.00') })
    const user = userEvent.setup()
    renderAt('/dat-hang')

    const alert = await within(await screen.findByRole('complementary', { name: 'Đơn hàng của bạn' })).findByRole('alert')
    expect(alert).toHaveTextContent(`Chưa kiểm tra được mã giảm giá. ${message}`)
    expect(alert).not.toHaveTextContent('không dùng được')
    expect(within(summary()).getByText('Chưa xác định')).toBeInTheDocument()
    expect(confirm()).toBeDisabled()
    expect(confirm()).toHaveAccessibleDescription('Chưa kiểm tra được mã giảm giá. Hãy thử lại hoặc bỏ mã.')

    await user.click(within(alert).getByRole('button', { name: 'Thử lại' }))
    await waitFor(() => expect(row('Giảm giá')).toHaveTextContent(`−${vnd(500000)}`))
    expect(confirm()).toBeEnabled()
    expect(sessionStorage.getItem(COUPON_KEY)).toBe('GIAM10')
  })

  test('"Bỏ mã" after a failed check lets the customer go on without a discount', async () => {
    sessionStorage.setItem(COUPON_KEY, 'GIAM10')
    mockApi({ '/cart/coupon-preview': { status: 502, body: { detail: 'Bad Gateway' } } })
    const user = userEvent.setup()
    renderAt('/dat-hang')

    const alert = await within(await screen.findByRole('complementary', { name: 'Đơn hàng của bạn' })).findByRole('alert')
    await user.click(within(alert).getByRole('button', { name: 'Bỏ mã' }))
    expect(row('Mã giảm giá')).toHaveTextContent('Chưa áp dụng')
    await waitFor(() => expect(confirm()).toBeEnabled())
    expect(sessionStorage.getItem(COUPON_KEY)).toBeNull()
  })

  test('a preview priced on other lines than the cart on screen asks for a reload before any total is shown', async () => {
    sessionStorage.setItem(COUPON_KEY, 'GIAM10')
    const repriced = cartOf([{ ...LINES[0], CurrentPrice: '42000000.00', LineTotal: '84000000.00' }, LINES[1]])
    // The price changes between the cart read and the preview; the cart reads the new price from the reload on.
    let changed = false
    const server = mockApi({
      '/cart': () => ({ body: changed ? repriced : cartOf(LINES) }),
      '/cart/coupon-preview': previewOf('84000000.00', '500000.00'),
    })
    const user = userEvent.setup()
    renderAt('/dat-hang')

    const alert = await within(await screen.findByRole('complementary', { name: 'Đơn hàng của bạn' })).findByRole('alert')
    expect(alert).toHaveTextContent('Giỏ hàng vừa thay đổi nên số tiền giảm chưa khớp.')
    expect(within(summary()).queryByText('Giảm giá')).not.toBeInTheDocument()
    expect(within(summary()).getByText('Chưa xác định')).toBeInTheDocument()
    expect(confirm()).toBeDisabled()

    changed = true
    await user.click(within(alert).getByRole('button', { name: 'Tải lại' }))
    await waitFor(() => expect(row('Giảm giá')).toHaveTextContent(`−${vnd(500000)}`))
    expect(row('Tạm tính (2 sản phẩm)')).toHaveTextContent(vnd(84000000))
    await waitFor(() => expect(within(summary()).getByText(vnd(83530000))).toBeInTheDocument())
    // This page read it twice (load, reload); the header cart entry once.
    expect(server.calls.filter((call) => call.endpoint === '/cart')).toHaveLength(3)
  })
})

describe('placing the order', () => {
  const COUPON_KEY = 'vietech-cart-coupon:Customer-id'
  const UUID = 'b7e1c0de-1111-4abc-9def-222233334444'
  const withCoupon = { '/cart/coupon-preview': { body: { Code: 'GIAM10', PromotionId: 'promo1', Subtotal: '83980000.00',
    EligibleSubtotal: '83980000.00', DiscountAmount: '500000.00' } } }
  const confirm = () => screen.getByRole('button', { name: /^(Xác nhận đặt hàng|Đang đặt hàng…)$/ })
  const cleanups = []
  afterEach(() => {
    while (cleanups.length) cleanups.pop()()
  })

  // Counts the header cart refresh events.
  function watchCartChanges() {
    const seen = { count: 0 }
    const listener = () => { seen.count += 1 }
    window.addEventListener('vietech-cart-changed', listener)
    cleanups.push(() => window.removeEventListener('vietech-cart-changed', listener))
    return seen
  }

  // The form with its defaults: saved address a2, standard shipping s1, COD m1 (and the coupon checked, if any).
  async function loaded() {
    await screen.findByText('Nguyễn Văn B • 0987654321')
    await screen.findByRole('radio', { name: /Giao hàng tiêu chuẩn/ })
    await screen.findByRole('radio', { name: /Thanh toán khi nhận hàng/ })
    await waitFor(() => expect(confirm()).toBeEnabled())
  }

  test('COD: only the form choices are sent, the coupon is used up and the order page shows the server figures', async () => {
    sessionStorage.setItem(COUPON_KEY, 'GIAM10')
    const server = mockApi(withCoupon)
    const changes = watchCartChanges()
    const user = userEvent.setup()
    const router = renderAt('/dat-hang')
    await loaded()
    expect(within(summary()).getByText(vnd(83510000))).toBeInTheDocument() // the page's own estimate

    await user.click(confirm())
    await waitFor(() => expect(router.state.location.pathname).toBe('/don-hang/o1'))
    expect(router.state.historyAction).toBe('REPLACE')
    const [post] = server.posts()
    expect(server.posts()).toHaveLength(1)
    expect(post.body).toEqual({ ShippingMethodId: 's1', PaymentMethodId: 'm1', AddressId: 'a2', CouponCode: 'GIAM10' })
    for (const key of ['Items', 'Lines', 'Subtotal', 'ShippingFee', 'DiscountAmount', 'TotalAmount', 'UnitPrice', 'Price']) {
      expect(post.body).not.toHaveProperty(key)
    }
    expect(sessionStorage.getItem(COUPON_KEY)).toBeNull()
    expect(changes.count).toBe(1)

    expect(await screen.findByRole('heading', { level: 1, name: 'Đặt hàng thành công' })).toBeInTheDocument()
    expect(screen.getByText('VT261016ABC123')).toBeInTheDocument()
    expect(screen.getByText(vnd(83500000))).toBeInTheDocument()
    expect(screen.queryByText(vnd(83510000))).not.toBeInTheDocument()
    expect(await screen.findByText('Thanh toán khi nhận hàng (COD)')).toBeInTheDocument()
    expect(screen.queryByText('Đã thanh toán')).not.toBeInTheDocument()
    // The order page reads the order again from the server; COD starts no payment.
    await waitFor(() => expect(server.reads('/orders/o1')).toBe(1))
    expect(server.calls.some((call) => call.endpoint.includes('payments'))).toBe(false)
  })

  test('another payment method: the order is placed but not paid; the order page then asks for its QR', async () => {
    const server = mockApi()
    const changes = watchCartChanges()
    const user = userEvent.setup()
    const router = renderAt('/dat-hang')
    await loaded()

    await user.click(screen.getByRole('radio', { name: /Chuyển khoản QR/ }))
    await user.click(confirm())
    await waitFor(() => expect(router.state.location.pathname).toBe('/don-hang/o1'))
    expect(server.posts().map((call) => call.body)).toEqual([{ ShippingMethodId: 's1', PaymentMethodId: 'm2', AddressId: 'a2' }])
    expect(changes.count).toBe(1)
    expect(await screen.findByText('VTPAY12345678')).toBeInTheDocument()
    expect(screen.getByText('Chờ thanh toán')).toBeInTheDocument()
    expect(screen.queryByText('Đã thanh toán')).not.toBeInTheDocument()
    // The confirmation page starts no payment: the QR is asked once, by the order page, after the order exists.
    const qrCalls = server.calls.filter((call) => call.endpoint === '/orders/o1/payments/qr')
    expect(qrCalls).toEqual([expect.objectContaining({ method: 'POST', body: undefined })])
    expect(server.calls.indexOf(qrCalls[0])).toBeGreaterThan(server.calls.indexOf(server.posts()[0]))
  })

  test('the order is sent once, however often the button is pressed or the form submitted', async () => {
    let answer
    const server = mockApi({ 'POST /orders': () => new Promise((resolve) => { answer = resolve }) })
    const user = userEvent.setup()
    const router = renderAt('/dat-hang')
    await loaded()

    const button = confirm()
    const form = button.closest('form')
    fireEvent.submit(form)
    fireEvent.submit(form) // before the page re-renders
    await waitFor(() => expect(button).toBeDisabled())
    expect(button).toHaveTextContent('Đang đặt hàng…')
    await user.click(button)
    fireEvent.submit(form)
    expect(server.posts()).toHaveLength(1)

    answer({ status: 201, body: ORDER })
    await waitFor(() => expect(router.state.location.pathname).toBe('/don-hang/o1'))
    expect(server.posts()).toHaveLength(1)
  })

  test.each([
    ['insufficient_stock', 400, { detail: `Không đủ tồn kho: ['${UUID}']`, code: 'insufficient_stock' },
      'Có sản phẩm không còn đủ số lượng trong kho. Vui lòng cập nhật giỏ hàng rồi đặt lại.', '/cart'],
    ['variant_not_available', 400, { detail: `Sản phẩm không còn bán: ['${UUID}']`, code: 'variant_not_available' },
      'Có sản phẩm trong đơn đã ngừng bán. Vui lòng cập nhật giỏ hàng rồi đặt lại.', '/cart'],
    ['shipping_method_not_available', 404, { detail: 'Phương thức vận chuyển không hợp lệ', code: 'shipping_method_not_available' },
      'Phương thức vận chuyển đã chọn hiện không còn khả dụng. Vui lòng chọn phương thức khác.', '/shipping-methods'],
    ['payment_method_not_available', 404, { detail: 'Phương thức thanh toán không hợp lệ', code: 'payment_method_not_available' },
      'Phương thức thanh toán đã chọn hiện không còn khả dụng. Vui lòng chọn phương thức khác.', '/payment-methods'],
    ['address_not_found', 404, { detail: 'Không tìm thấy địa chỉ', code: 'address_not_found' },
      'Địa chỉ đã chọn không còn trong sổ địa chỉ. Vui lòng chọn hoặc nhập địa chỉ khác.', '/users/me/addresses'],
    ['a validation error', 422, { detail: [{ loc: ['body', 'Items'], msg: 'Extra inputs are not permitted', type: 'extra_forbidden' }] },
      'Thông tin đặt hàng chưa hợp lệ. Vui lòng kiểm tra lại rồi thử lại.', null],
    ['an expired session', 401, { detail: 'Phiên đăng nhập không hợp lệ' },
      'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để đặt hàng.', null],
    ['a forbidden account', 403, { detail: 'Bạn không có quyền thực hiện thao tác này', code: 'permission_denied' },
      'Tài khoản hiện tại không thể đặt hàng. Vui lòng đăng nhập bằng tài khoản khách hàng.', null],
    ['an unknown business error', 409, { detail: `Dữ liệu đã tồn tại ${UUID}`, code: 'duplicate_value' },
      'Chưa đặt được hàng. Vui lòng kiểm tra lại thông tin rồi thử lại.', null],
  ])('%s: the order is refused, explained, and nothing of a placed order happens', async (_, status, body, message, reloaded) => {
    sessionStorage.setItem(COUPON_KEY, 'GIAM10')
    const server = mockApi({ ...withCoupon, 'POST /orders': { status, body } })
    const changes = watchCartChanges()
    const user = userEvent.setup()
    const router = renderAt('/dat-hang')
    await loaded()
    const before = reloaded && server.reads(reloaded)

    await user.click(confirm())
    if (reloaded) await waitFor(() => expect(server.reads(reloaded)).toBe(before + 1))
    // Queried again until the reloaded data is shown (a reloaded cart shows the message above, then in the summary).
    await waitFor(() => expect(screen.getByText(message)).toBeInTheDocument())
    await waitFor(() => expect(confirm()).toBeInTheDocument())
    expect(screen.getByText(message)).toBeInTheDocument()
    expect(screen.queryByText(new RegExp(UUID))).not.toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/dat-hang')
    expect(server.posts()).toHaveLength(1)
    expect(sessionStorage.getItem(COUPON_KEY)).toBe('GIAM10')
    expect(changes.count).toBe(0)
  })

  test('a field error stays with its field until the customer changes it; sending again is the customer’s choice', async () => {
    const server = mockApi({ 'POST /orders': (count) => count === 1
      ? { status: 400, body: { detail: 'Đơn hàng 0 đồng không thể thanh toán chuyển khoản.', code: 'order_total_zero' } }
      : { status: 201, body: ORDER } })
    const user = userEvent.setup()
    const router = renderAt('/dat-hang')
    await loaded()

    const transfer = screen.getByRole('radio', { name: /Chuyển khoản QR/ })
    await user.click(transfer)
    await user.click(confirm())
    const payments = screen.getByRole('group', { name: 'Phương thức thanh toán' })
    await waitFor(() => expect(payments).toHaveAccessibleDescription(
      'Đơn hàng 0 đồng không thể thanh toán chuyển khoản. Vui lòng chọn thanh toán khi nhận hàng (COD) hoặc bỏ mã giảm giá.'))
    expect(transfer).toBeChecked()
    expect(server.posts()).toHaveLength(1)

    await user.click(screen.getByRole('radio', { name: /Thanh toán khi nhận hàng/ }))
    expect(payments).not.toHaveAccessibleDescription()
    await user.click(confirm())
    await waitFor(() => expect(router.state.location.pathname).toBe('/don-hang/o1'))
    expect(server.posts().map((call) => call.body.PaymentMethodId)).toEqual(['m2', 'm1'])
  })

  test('a coupon refused by the order is checked again and shown by the coupon check; the code is kept', async () => {
    sessionStorage.setItem(COUPON_KEY, 'GIAM10')
    const server = mockApi({
      '/cart/coupon-preview': (count) => count === 1 ? withCoupon['/cart/coupon-preview']
        : { status: 400, body: { detail: 'Mã giảm giá đã hết lượt sử dụng', code: 'coupon_usage_exceeded' } },
      'POST /orders': { status: 400, body: { detail: 'Mã giảm giá đã hết lượt sử dụng', code: 'coupon_usage_exceeded' } },
    })
    const user = userEvent.setup()
    renderAt('/dat-hang')
    await loaded()

    await user.click(confirm())
    expect(await within(summary()).findByRole('alert')).toHaveTextContent('Mã giảm giá đã hết lượt sử dụng')
    expect(server.calls.filter((call) => call.endpoint === '/cart/coupon-preview')).toHaveLength(2)
    expect(confirm()).toBeDisabled()
    expect(confirm()).toHaveAccessibleDescription('Mã giảm giá GIAM10 không dùng được. Hãy bỏ mã hoặc quay lại giỏ hàng để đổi mã.')
    expect(sessionStorage.getItem(COUPON_KEY)).toBe('GIAM10')
    expect(server.posts()).toHaveLength(1)
  })

  test('an empty cart (lines ordered elsewhere) sends the customer back to the cart with the reason', async () => {
    let ordered = false
    mockApi({
      '/cart': () => ({ body: ordered ? cartOf(LINES.map((line) => ({ ...line, IsSelected: false }))) : cartOf(LINES) }),
      'POST /orders': () => {
        ordered = true
        return { status: 400, body: { detail: 'Giỏ hàng chưa có sản phẩm được chọn', code: 'cart_empty' } }
      },
    })
    const user = userEvent.setup()
    renderAt('/dat-hang')
    await loaded()

    await user.click(confirm())
    expect(await screen.findByRole('heading', { name: 'Chưa có sản phẩm nào được chọn' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Giỏ hàng không còn sản phẩm nào được chọn để đặt.')
  })

  describe('when the answer is lost, the order may exist: it is checked, never sent again on its own', () => {
    test.each([
      ['a lost connection', { network: true }],
      ['a server error', { status: 500, body: { detail: 'Internal Server Error' } }],
      ['a gateway timeout', { status: 504, body: null }],
    ])('%s: warning, no resend, then the latest order is found and the cart is read again', async (_, failure) => {
      sessionStorage.setItem(COUPON_KEY, 'GIAM10')
      let ordered = false
      const server = mockApi({
        ...withCoupon,
        '/cart': () => ({ body: ordered ? cartOf([LINES[1]]) : cartOf(LINES) }),
        'POST /orders': () => {
          ordered = true
          return failure
        },
      })
      const changes = watchCartChanges()
      const user = userEvent.setup()
      const router = renderAt('/dat-hang')
      await loaded()

      await user.click(confirm())
      const warning = await within(summary()).findByRole('alert')
      expect(warning).toHaveTextContent('chưa xác định được đơn hàng đã được tạo hay chưa')
      expect(confirm()).toBeDisabled()
      expect(confirm()).toHaveAccessibleDescription('Hãy kiểm tra đơn hàng trước khi đặt lại.')
      fireEvent.submit(confirm().closest('form'))
      expect(server.posts()).toHaveLength(1)
      expect(sessionStorage.getItem(COUPON_KEY)).toBe('GIAM10')
      expect(changes.count).toBe(0)

      await user.click(within(summary()).getByRole('button', { name: 'Kiểm tra đơn hàng' }))
      // The order was placed: its lines left the cart, and the newest order is offered.
      expect(await screen.findByRole('heading', { name: 'Chưa có sản phẩm nào được chọn' })).toBeInTheDocument()
      expect(screen.getByText('VT261016ABC123')).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Xem đơn hàng' })).toHaveAttribute('href', '/don-hang/o1')
      expect(server.calls.find((call) => call.endpoint === '/orders' && call.method === 'GET').query).toEqual({ page: '1', page_size: '1' })
      expect(server.posts()).toHaveLength(1)
      expect(router.state.location.pathname).toBe('/dat-hang')
    })

    test('when no order was created the customer may send it again, by their own click only', async () => {
      const server = mockApi({
        'POST /orders': (count) => count === 1 ? { network: true } : { status: 201, body: ORDER },
        'GET /orders': { body: { Items: [], Total: 0, Page: 1, PageSize: 1 } },
      })
      const user = userEvent.setup()
      const router = renderAt('/dat-hang')
      await loaded()

      await user.click(confirm())
      await user.click(await within(summary()).findByRole('button', { name: 'Kiểm tra đơn hàng' }))
      // The cart is read again after the check, so the message is queried until the form is back.
      await waitFor(() => expect(within(summary())
        .getByText('Bạn chưa có đơn hàng nào, nên đơn vừa rồi chưa được tạo. Bạn có thể đặt hàng lại.')).toBeInTheDocument())
      await waitFor(() => expect(confirm()).toBeEnabled())
      expect(server.posts()).toHaveLength(1)

      await user.click(confirm())
      await waitFor(() => expect(router.state.location.pathname).toBe('/don-hang/o1'))
      expect(server.posts()).toHaveLength(2)
    })

    test('a failed check can be repeated and keeps the order blocked', async () => {
      const server = mockApi({ 'POST /orders': { status: 503, body: { detail: 'Không thể xử lý dữ liệu lúc này. Vui lòng thử lại' } },
        'GET /orders': { status: 503, body: { detail: 'Service Unavailable' } } })
      const user = userEvent.setup()
      renderAt('/dat-hang')
      await loaded()

      await user.click(confirm())
      await user.click(await within(summary()).findByRole('button', { name: 'Kiểm tra đơn hàng' }))
      expect(await within(summary()).findByText(/Chưa kiểm tra được đơn hàng/)).toBeInTheDocument()
      expect(within(summary()).getByRole('button', { name: 'Kiểm tra lại' })).toBeInTheDocument()
      expect(confirm()).toBeDisabled()
      expect(server.posts()).toHaveLength(1)
    })

    test('a session that changed while waiting (local 401 after the request) leaves the order unknown', async () => {
      const server = mockApi()
      // The order is placed, then withAccessToken discards the answer because the session changed meanwhile.
      const withAccessToken = vi.fn(async (call) => {
        const result = await call('access-for-test')
        if (result?.OrderId) throw new AuthApiError('Phiên đăng nhập đã thay đổi. Vui lòng thử lại.', 401)
        return result
      })
      const user = userEvent.setup()
      const router = renderAt('/dat-hang', makeAuth({ role: 'Customer', withAccessToken }))
      await loaded()

      await user.click(confirm())
      const warning = await within(summary()).findByRole('alert')
      expect(warning).toHaveTextContent('Phiên đăng nhập vừa thay đổi nên chưa xác định được đơn hàng đã được tạo hay chưa.')
      expect(within(summary()).getByRole('link', { name: 'Đăng nhập lại' })).toHaveAttribute('href', '/dang-nhap?next=%2Fdat-hang')
      expect(within(summary()).getByRole('button', { name: 'Kiểm tra đơn hàng' })).toBeInTheDocument()
      expect(confirm()).toBeDisabled()
      expect(server.posts()).toHaveLength(1)
      expect(router.state.location.pathname).toBe('/dat-hang')
    })
  })
})
