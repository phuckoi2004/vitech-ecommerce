import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { AuthContext } from '../../auth/context.js'
import { formatDateTime, formatMoney } from '../../lib/format.js'
import { appRoutes } from '../../routes.jsx'
import { makeAuth } from '../../test/auth.js'

// Text as the default Testing Library normalizer sees it (Intl puts a no-break space before "₫").
const vnd = (value) => formatMoney(value).replace(/\s/g, ' ')

const PAYMENT = [
  { PaymentMethodId: 'm1', Code: 'COD', Name: 'Thanh toán khi nhận hàng (COD)', Description: null, IsActive: true, DisplayOrder: 1 },
  { PaymentMethodId: 'm2', Code: 'SEPAY', Name: 'Chuyển khoản QR', Description: null, IsActive: true, DisplayOrder: 2 },
]
const ORDER = {
  OrderId: 'o1', OrderCode: 'VT261016ABC123', TotalAmount: '313334.00', OrderStatus: 'Pending', PaymentStatus: 'Pending',
  OrderedAt: '2026-10-16T03:00:00Z', AddressId: 'a1', ShippingMethodId: 's1', PaymentMethodId: 'm2', CouponId: null,
  Subtotal: '333333.00', ShippingFee: '30000.00', DiscountAmount: '49999.00', ReceiverName: 'Nguyễn Văn B',
  ReceiverPhone: '0987654321', ShippingAddress: '12 Lê Lợi, Phường Bến Nghé, TP Hồ Chí Minh', CustomerNote: null,
  CancelReason: null, ConfirmedAt: null, ShippedAt: null, DeliveredAt: null, CompletedAt: null, CancelledAt: null,
  Items: [], StatusHistories: [],
}
const COD_ORDER = { ...ORDER, PaymentMethodId: 'm1' }
const PAID = { ...ORDER, PaymentStatus: 'Paid' }
const CANCELLED = { ...ORDER, OrderStatus: 'Cancelled', PaymentStatus: 'Cancelled', CancelledAt: '2026-10-16T03:16:00Z' }
const QR = {
  PaymentTransactionId: 't1', OrderId: 'o1', PaymentMethodId: 'm2', TransactionType: 'Payment', Amount: '313334.00',
  Status: 'Pending', QrData: 'https://qr.sepay.vn/img?acc=0123456789&bank=Vietcombank&amount=313334&des=VTPAY12345678',
  PaidAt: null, CreatedAt: '2026-10-16T03:00:05Z', RefundOfPaymentTransactionId: null,
  TransferContent: 'VTPAY12345678', Bank: 'Vietcombank', AccountNumber: '0123456789', TransferAmount: 313334,
  ExpiresAt: '2026-10-16T03:15:00Z',
}

// API of the page. `overrides['METHOD /endpoint']` or `overrides['/endpoint']` replaces a response ({status, body}, or
// {network: true}), or is a function of the call count returning one, or a promise of one. Responses are plain
// objects whose body is read without streams, so under fake timers only the clock decides when a poll runs.
function mockApi(overrides = {}) {
  const calls = []
  const counts = {}
  vi.stubGlobal('fetch', vi.fn(async (input, options = {}) => {
    const url = new URL(input, 'http://localhost')
    const endpoint = url.pathname.replace(/^\/api/, '')
    const method = options.method ?? 'GET'
    calls.push({ endpoint, method, body: options.body, signal: options.signal, token: options.headers?.Authorization })
    const key = `${method} ${endpoint}` in overrides ? `${method} ${endpoint}` : endpoint
    counts[key] = (counts[key] ?? 0) + 1
    const override = await (typeof overrides[key] === 'function' ? overrides[key](counts[key]) : overrides[key])
    if (override?.network) throw new TypeError('Failed to fetch')
    const [status, body] = override ? [override.status ?? 200, override.body] : answer(endpoint, method)
    return { ok: status >= 200 && status < 300, status, headers: new Headers(), json: async () => body }
  }))
  const count = (method, endpoint) => calls.filter((call) => call.method === method && call.endpoint === endpoint).length
  return {
    calls,
    reads: () => count('GET', '/orders/o1'),
    qrRequests: () => calls.filter((call) => call.method === 'POST' && call.endpoint === '/orders/o1/payments/qr'),
    cancels: () => calls.filter((call) => call.method === 'POST' && call.endpoint === '/orders/o1/cancel'),
  }
}

function answer(endpoint, method) {
  if (endpoint === '/orders/o1' && method === 'GET') return [200, ORDER]
  if (endpoint === '/orders/o1/payments/qr' && method === 'POST') return [201, QR]
  if (endpoint === '/payment-methods') return [200, PAYMENT]
  if (endpoint === '/cart') return [200, { CartId: 'c1', Items: [], SelectedQuantity: 0, SelectedSubtotal: '0.00' }]
  if (endpoint === '/users/me/notifications/unread-count') return [200, { Count: 0 }]
  return [404, { detail: 'Không tìm thấy' }]
}

function renderAt(url, { auth = makeAuth({ role: 'Customer' }), state, strict = false } = {}) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [state ? { pathname: url, state } : url] })
  const tree = <AuthContext.Provider value={auth}><RouterProvider router={router} /></AuthContext.Provider>
  return { router, ...render(strict ? <StrictMode>{tree}</StrictMode> : tree) }
}

// Timers and dates on a fake clock set to `at` (promises stay real), for the polling and deadline tests.
function fakeClock(at) {
  vi.useRealTimers()
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
  vi.setSystemTime(new Date(at))
}
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))
// Lets the pending requests answer and the page render, without moving the clock.
async function settle() {
  for (let step = 0; step < 4; step += 1) await advance(0)
}

const summaryValue = (label) => screen.getByText(label).nextElementSibling

beforeEach(() => {
  // Dates come from a fixed clock, 10 minutes before the QR deadline (03:15); timers stay real unless a test fakes them.
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-16T03:05:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('order page: COD', () => {
  test('opened from the confirmation page it still reads the order from the server; COD needs no QR and no polling', async () => {
    fakeClock('2026-10-16T03:01:00Z')
    const server = mockApi({ 'GET /orders/o1': { body: { ...COD_ORDER, TotalAmount: '313000.00' } } })
    renderAt('/don-hang/o1', { state: { order: COD_ORDER, paymentCode: 'COD' } })

    // The order passed along is shown at once, then replaced by the server's.
    expect(screen.getByRole('heading', { level: 1, name: 'Đặt hàng thành công' })).toBeInTheDocument()
    expect(screen.getByText('VT261016ABC123')).toBeInTheDocument()
    await settle()
    expect(server.reads()).toBe(1)
    expect(summaryValue('Tổng thanh toán')).toHaveTextContent(vnd(313000))
    expect(summaryValue('Trạng thái đơn hàng')).toHaveTextContent('Chờ xác nhận')
    expect(summaryValue('Phương thức thanh toán')).toHaveTextContent('Thanh toán khi nhận hàng (COD)')
    expect(summaryValue('Trạng thái thanh toán')).toHaveTextContent('Thanh toán khi nhận hàng')
    expect(screen.getByText(/khi nhận hàng\. VieTech sẽ liên hệ/)).toBeInTheDocument()
    expect(screen.queryByText('Đã thanh toán')).not.toBeInTheDocument()

    await advance(15000)
    expect(server.reads()).toBe(1)
    expect(server.qrRequests()).toHaveLength(0)
    expect(document.title).toBe('Đơn hàng VT261016ABC123 | VieTech')
  })

  test('the payment method comes from the order PaymentMethodId and the methods list, not from the page that opened it', async () => {
    const server = mockApi({ 'GET /orders/o1': { body: COD_ORDER } })
    // A stale hint that it was a transfer order: the list says COD.
    renderAt('/don-hang/o1', { state: { order: COD_ORDER, paymentCode: 'SEPAY' } })
    expect(await screen.findByText(/VieTech sẽ liên hệ để xác nhận đơn hàng/)).toBeInTheDocument()
    expect(server.qrRequests()).toHaveLength(0)
  })
})

describe('order page: SePay QR', () => {
  test('a transfer order shows the QR and the transfer details sent by the server, not paid yet', async () => {
    const server = mockApi()
    renderAt('/don-hang/o1')

    const qr = await screen.findByRole('region', { name: 'Quét mã QR để thanh toán' })
    expect(within(qr).getByRole('img', { name: 'Mã QR chuyển khoản cho đơn hàng' })).toHaveAttribute('src', QR.QrData)
    expect(within(qr).getByText('Vietcombank')).toBeInTheDocument()
    expect(within(qr).getByText('0123456789')).toBeInTheDocument()
    expect(within(qr).getByText(vnd(313334))).toBeInTheDocument()
    expect(within(qr).getByText('VTPAY12345678')).toBeInTheDocument()
    expect(within(qr).getByText(new RegExp(formatDateTime(QR.ExpiresAt)))).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Chi tiết đơn hàng' })).toBeInTheDocument()
    expect(summaryValue('Trạng thái thanh toán')).toHaveTextContent('Chờ thanh toán')
    expect(screen.queryByText('Đã thanh toán')).not.toBeInTheDocument()

    expect(server.qrRequests()).toHaveLength(1)
    expect(server.qrRequests()[0]).toMatchObject({ body: undefined, token: 'Bearer access-for-test' })
    expect(server.calls.some((call) => call.method === 'POST' && call.endpoint === '/orders')).toBe(false)
  })

  test('the QR is asked once, also when StrictMode runs the effects twice', async () => {
    const server = mockApi()
    renderAt('/don-hang/o1', { strict: true })
    expect(await screen.findByText('VTPAY12345678')).toBeInTheDocument()
    expect(server.qrRequests()).toHaveLength(1)
  })

  test('opening the order again gets the same pending QR back; no order is created', async () => {
    const server = mockApi()
    renderAt('/don-hang/o1')
    expect(await screen.findByText('VTPAY12345678')).toBeInTheDocument()
    cleanup()

    renderAt('/don-hang/o1')
    expect(await screen.findByText('VTPAY12345678')).toBeInTheDocument()
    expect(server.qrRequests()).toHaveLength(2)
    expect(server.calls.some((call) => call.method === 'POST' && call.endpoint === '/orders')).toBe(false)
  })

  test('missing bank, account, deadline or QR image are said plainly; the transfer content and amount stay', async () => {
    mockApi({ 'POST /orders/o1/payments/qr': { status: 201, body: { ...QR, Bank: null, AccountNumber: null, ExpiresAt: null, QrData: null } } })
    renderAt('/don-hang/o1')

    const qr = await screen.findByRole('region', { name: 'Quét mã QR để thanh toán' })
    expect(within(qr).getAllByText('Xem trong mã QR')).toHaveLength(2)
    expect(within(qr).getByText(/Không hiển thị được mã QR/)).toBeInTheDocument()
    expect(within(qr).queryByRole('img')).not.toBeInTheDocument()
    expect(within(qr).queryByText('Hạn thanh toán')).not.toBeInTheDocument()
    expect(within(qr).getByText('VTPAY12345678')).toBeInTheDocument()
    expect(within(qr).getByText(vnd(313334))).toBeInTheDocument()
  })

  test.each([
    ['the gateway is not configured', { status: 400, body: { detail: 'Chưa cấu hình cổng thanh toán', code: 'payment_gateway_not_configured' } },
      'Thanh toán chuyển khoản hiện chưa sẵn sàng.'],
    ['a QR is being created', { status: 409, body: { detail: 'Đang xử lý', code: 'qr_payment_in_progress' } }, 'Mã QR đang được tạo.'],
    ['the gateway failed', { status: 502, body: { detail: 'Không tạo được', code: 'qr_payment_unavailable' } }, 'Chưa tạo được mã QR.'],
    ['the connection failed', { network: true }, 'Chưa lấy được mã QR thanh toán.'],
  ])('when %s the customer can ask again and gets the QR', async (_, failure, message) => {
    const server = mockApi({ 'POST /orders/o1/payments/qr': (count) => count === 1 ? failure : { status: 201, body: QR } })
    const user = userEvent.setup()
    renderAt('/don-hang/o1')

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    await user.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('VTPAY12345678')).toBeInTheDocument()
    expect(server.qrRequests()).toHaveLength(2)
  })

  test('an order that cannot be paid by transfer says so, without a retry', async () => {
    mockApi({ 'POST /orders/o1/payments/qr': { status: 400, body: { detail: 'Đơn hàng 0 đồng', code: 'order_total_zero' } } })
    renderAt('/don-hang/o1')
    expect(await screen.findByRole('alert')).toHaveTextContent('Đơn hàng này không thể thanh toán chuyển khoản.')
    expect(screen.queryByRole('button', { name: 'Thử lại' })).not.toBeInTheDocument()
  })

  test('when the QR answer says the order is no longer payable, the order is read again (here: paid)', async () => {
    const server = mockApi({
      'GET /orders/o1': (count) => ({ body: count === 1 ? ORDER : PAID }),
      'POST /orders/o1/payments/qr': { status: 400, body: { detail: 'x', code: 'order_not_payable' } },
    })
    renderAt('/don-hang/o1')
    expect(await screen.findByText('VieTech đã nhận được thanh toán cho đơn hàng này. Cảm ơn bạn!')).toBeInTheDocument()
    expect(server.reads()).toBe(2)
    expect(summaryValue('Trạng thái thanh toán')).toHaveTextContent('Đã thanh toán')
  })

  test('a paid order shows no QR and cannot be cancelled', async () => {
    const server = mockApi({ 'GET /orders/o1': { body: PAID } })
    renderAt('/don-hang/o1')
    expect(await screen.findByText(/đã nhận được thanh toán/)).toBeInTheDocument()
    expect(server.qrRequests()).toHaveLength(0)
    expect(screen.queryByRole('button', { name: 'Huỷ đơn hàng' })).not.toBeInTheDocument()
  })

  test('a method missing from the list uses the Code the confirmation page passed; without one nothing is guessed', async () => {
    const order = { ...ORDER, PaymentMethodId: 'm-retired' }
    const server = mockApi({ 'GET /orders/o1': { body: order } })
    renderAt('/don-hang/o1')
    expect(await screen.findByText('Không xác định được phương thức thanh toán của đơn hàng.')).toBeInTheDocument()
    expect(server.qrRequests()).toHaveLength(0)
    cleanup()

    renderAt('/don-hang/o1', { state: { order, paymentCode: 'SEPAY' } })
    expect(await screen.findByText('VTPAY12345678')).toBeInTheDocument()
  })

  test('the transfer content can be copied; a refused clipboard gives a manual hint', async () => {
    mockApi()
    const user = userEvent.setup()
    renderAt('/don-hang/o1')
    const copy = await screen.findByRole('button', { name: 'Sao chép nội dung chuyển khoản VTPAY12345678' })

    await user.click(copy)
    expect(await navigator.clipboard.readText()).toBe('VTPAY12345678')
    expect(screen.getByText('Đã sao chép nội dung chuyển khoản.')).toBeInTheDocument()

    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValueOnce(new Error('denied'))
    await user.click(copy)
    expect(await screen.findByText(/Không sao chép được/)).toBeInTheDocument()
  })
})

describe('order page: waiting for the transfer', () => {
  test('the order is read every 3 seconds until the server says Paid, then polling stops', async () => {
    fakeClock('2026-10-16T03:05:00Z')
    const server = mockApi({ 'GET /orders/o1': (count) => ({ body: count >= 3 ? PAID : ORDER }) })
    renderAt('/don-hang/o1')
    await settle()
    expect(screen.getByText('VTPAY12345678')).toBeInTheDocument()
    expect(screen.getByText('10:00')).toBeInTheDocument()
    expect(server.reads()).toBe(1)

    await advance(2999)
    expect(server.reads()).toBe(1)
    await advance(1)
    await settle()
    expect(server.reads()).toBe(2)
    expect(screen.queryByText('Đã thanh toán')).not.toBeInTheDocument()

    await advance(3000)
    await settle()
    expect(server.reads()).toBe(3)
    expect(screen.getByText('VieTech đã nhận được thanh toán cho đơn hàng này. Cảm ơn bạn!')).toBeInTheDocument()
    expect(summaryValue('Trạng thái thanh toán')).toHaveTextContent('Đã thanh toán')
    expect(screen.queryByText('VTPAY12345678')).not.toBeInTheDocument()

    await advance(15000)
    expect(server.reads()).toBe(3)
    expect(server.qrRequests()).toHaveLength(1)
  })

  test('coming back to the page (e.g. from the banking app) reads the order at once, one request at a time', async () => {
    fakeClock('2026-10-16T03:05:00Z')
    const server = mockApi({ 'GET /orders/o1': (count) => ({ body: count >= 2 ? PAID : ORDER }) })
    let state = 'visible'
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state })
    const changeVisibility = (value, times = 1) => act(async () => {
      state = value
      for (let index = 0; index < times; index += 1) document.dispatchEvent(new Event('visibilitychange'))
    })
    try {
      renderAt('/don-hang/o1')
      await settle()
      expect(server.reads()).toBe(1)

      await changeVisibility('hidden')
      await advance(1000)
      expect(server.reads()).toBe(1)
      // Back after 1 s: read now rather than 2 s later, and only once even if the event repeats.
      await changeVisibility('visible', 2)
      await settle()
      expect(server.reads()).toBe(2)
      expect(screen.getByText('VieTech đã nhận được thanh toán cho đơn hàng này. Cảm ơn bạn!')).toBeInTheDocument()

      await changeVisibility('hidden')
      await changeVisibility('visible')
      await advance(15000)
      expect(server.reads()).toBe(2) // paid: no more reads
    } finally {
      delete document.visibilityState
    }
  })

  test('a failed read keeps the QR and the next poll goes on', async () => {
    fakeClock('2026-10-16T03:05:00Z')
    const server = mockApi({ 'GET /orders/o1': (count) => count === 2 ? { status: 503, body: { detail: 'Service Unavailable' } } : { body: ORDER } })
    renderAt('/don-hang/o1')
    await settle()

    await advance(3000)
    await settle()
    expect(screen.getByText(/Chưa cập nhật được trạng thái mới nhất của đơn hàng\. Đang thử lại…/)).toBeInTheDocument()
    expect(screen.getByText('VTPAY12345678')).toBeInTheDocument()
    await advance(3000)
    await settle()
    expect(server.reads()).toBe(3)
    expect(screen.queryByText(/Chưa cập nhật được trạng thái/)).not.toBeInTheDocument()
  })

  test('leaving the page stops polling and aborts the read in progress', async () => {
    fakeClock('2026-10-16T03:05:00Z')
    const server = mockApi({ 'GET /orders/o1': (count) => count === 1 ? { body: ORDER } : new Promise(() => {}) })
    const view = renderAt('/don-hang/o1')
    await settle()
    await advance(3000)
    expect(server.reads()).toBe(2)
    const inProgress = server.calls.filter((call) => call.endpoint === '/orders/o1').at(-1)
    expect(inProgress.signal.aborted).toBe(false)

    view.unmount()
    expect(inProgress.signal.aborted).toBe(true)
    await advance(30000)
    expect(server.reads()).toBe(2)
  })

  test('an order cancelled meanwhile (e.g. by the expiry job) ends the QR and the polling', async () => {
    fakeClock('2026-10-16T03:05:00Z')
    const server = mockApi({ 'GET /orders/o1': (count) => ({ body: count === 1 ? ORDER
      : { ...CANCELLED, CancelReason: 'Hết hạn thanh toán QR (15 phút)' } }) })
    renderAt('/don-hang/o1')
    await settle()
    await advance(3000)
    await settle()

    expect(screen.getByText('Đơn hàng đã bị huỷ. Lý do: Hết hạn thanh toán QR (15 phút)')).toBeInTheDocument()
    expect(summaryValue('Trạng thái đơn hàng')).toHaveTextContent('Đã huỷ')
    expect(screen.queryByText('VTPAY12345678')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Huỷ đơn hàng' })).not.toBeInTheDocument()
    await advance(15000)
    expect(server.reads()).toBe(2)
  })

  test('when the deadline passes the QR is withdrawn, the order read once more, and polling stops', async () => {
    fakeClock('2026-10-16T03:14:58.500Z')
    const server = mockApi({ 'GET /orders/o1': (count) => ({ body: count >= 3 ? CANCELLED : ORDER }) })
    renderAt('/don-hang/o1')
    await settle()
    expect(screen.getByText('00:02')).toBeInTheDocument()

    await advance(1000)
    expect(screen.getByText('00:01')).toBeInTheDocument()
    await advance(1000)
    await settle()
    expect(screen.getByText(/Đã hết thời gian thanh toán/)).toBeInTheDocument()
    expect(screen.queryByText('VTPAY12345678')).not.toBeInTheDocument()
    expect(screen.queryByText('Đã thanh toán')).not.toBeInTheDocument()
    expect(server.reads()).toBe(2) // the first read, then once at the deadline
    await advance(15000)
    expect(server.reads()).toBe(2)

    // The customer checks again: the expiry job has cancelled it.
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra lại trạng thái' }))
    await settle()
    expect(server.reads()).toBe(3)
    expect(screen.getByText('Đơn hàng đã bị huỷ.')).toBeInTheDocument()
  })

  test('opened after the deadline: the QR is refused as expired, without a retry, and the order is read once more', async () => {
    const server = mockApi({ 'POST /orders/o1/payments/qr': { status: 400, body: { detail: 'Quá hạn', code: 'order_payment_expired' } } })
    renderAt('/don-hang/o1')
    expect(await screen.findByText('Đơn hàng đã hết thời gian thanh toán (15 phút) và sẽ được huỷ tự động.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Thử lại' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kiểm tra lại trạng thái' })).toBeInTheDocument()
    await vi.waitFor(() => expect(server.reads()).toBe(2))
  })
})

describe('order page: cancelling', () => {
  test('the customer confirms first; the order is cancelled once, with a busy state, and the QR goes away', async () => {
    let finish
    const server = mockApi({ 'POST /orders/o1/cancel': () => new Promise((resolve) => { finish = resolve }) })
    const user = userEvent.setup()
    renderAt('/don-hang/o1')
    await screen.findByText('VTPAY12345678')

    await user.click(screen.getByRole('button', { name: 'Huỷ đơn hàng' }))
    const confirm = screen.getByRole('group', { name: 'Xác nhận huỷ đơn hàng' })
    expect(within(confirm).getByText('Huỷ đơn hàng VT261016ABC123? Thao tác này không thể hoàn tác.')).toBeInTheDocument()
    expect(within(confirm).getByText(/Nếu bạn đã chuyển khoản, đừng huỷ đơn/)).toBeInTheDocument()
    await user.click(within(confirm).getByRole('button', { name: 'Không huỷ' }))
    expect(screen.queryByRole('group', { name: 'Xác nhận huỷ đơn hàng' })).not.toBeInTheDocument()
    expect(server.cancels()).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Huỷ đơn hàng' }))
    await user.click(screen.getByRole('button', { name: 'Xác nhận huỷ' }))
    expect(screen.getByRole('button', { name: 'Đang huỷ…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Không huỷ' })).toBeDisabled()
    expect(server.cancels()).toEqual([expect.objectContaining({ body: '{}', token: 'Bearer access-for-test' })])

    finish({ status: 200, body: CANCELLED })
    expect(await screen.findByText('Đơn hàng đã bị huỷ.')).toBeInTheDocument()
    expect(screen.queryByText('VTPAY12345678')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Huỷ đơn hàng' })).not.toBeInTheDocument()
    expect(server.cancels()).toHaveLength(1)
  })

  test('a refused cancellation is explained and the order is read again', async () => {
    const server = mockApi({
      'GET /orders/o1': (count) => ({ body: count === 1 ? COD_ORDER : { ...COD_ORDER, OrderStatus: 'Confirmed' } }),
      'POST /orders/o1/cancel': { status: 400, body: { detail: 'Không thể hủy đơn ở trạng thái Confirmed', code: 'order_not_cancellable' } },
    })
    const user = userEvent.setup()
    renderAt('/don-hang/o1')
    await screen.findByText(/VieTech sẽ liên hệ/)

    await user.click(screen.getByRole('button', { name: 'Huỷ đơn hàng' }))
    expect(screen.queryByText(/đừng huỷ đơn/)).not.toBeInTheDocument() // COD: no transfer warning
    await user.click(screen.getByRole('button', { name: 'Xác nhận huỷ' }))
    await vi.waitFor(() => expect(server.reads()).toBe(2))
    expect(await screen.findByText('Đã xác nhận')).toBeInTheDocument()
    expect(screen.queryByText(/Confirmed/)).not.toBeInTheDocument()
  })
})

describe('order page: a payment landing while cancelling', () => {
  test('a cancellation refused because the order was just paid shows it as paid, with no cancel action', async () => {
    const server = mockApi({
      'GET /orders/o1': (count) => ({ body: count === 1 ? ORDER : PAID }),
      'POST /orders/o1/cancel': { status: 400, body: { detail: 'Đơn hàng đã được thanh toán nên không thể tự hủy.', code: 'order_paid_not_cancellable' } },
    })
    const user = userEvent.setup()
    renderAt('/don-hang/o1')
    await screen.findByText('VTPAY12345678')

    await user.click(screen.getByRole('button', { name: 'Huỷ đơn hàng' }))
    await user.click(screen.getByRole('button', { name: 'Xác nhận huỷ' }))
    expect(await screen.findByText('VieTech đã nhận được thanh toán cho đơn hàng này. Cảm ơn bạn!')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Huỷ đơn hàng' })).not.toBeInTheDocument()
    expect(screen.queryByText('Đơn hàng đã bị huỷ.')).not.toBeInTheDocument()
    expect(server.cancels()).toHaveLength(1)
  })

  test('when the order cannot be read again, the refusal itself says why', async () => {
    mockApi({
      'GET /orders/o1': (count) => count === 1 ? { body: COD_ORDER } : { network: true },
      'POST /orders/o1/cancel': { status: 400, body: { detail: 'Đơn hàng đã được thanh toán nên không thể tự hủy.', code: 'order_paid_not_cancellable' } },
    })
    const user = userEvent.setup()
    renderAt('/don-hang/o1')
    await screen.findByText(/VieTech sẽ liên hệ/)

    await user.click(screen.getByRole('button', { name: 'Huỷ đơn hàng' }))
    await user.click(screen.getByRole('button', { name: 'Xác nhận huỷ' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Đơn hàng đã được thanh toán nên không thể tự huỷ. Vui lòng liên hệ VieTech để được hỗ trợ.')
  })
})

describe('order page: cancelled after being paid', () => {
  const PAID_NOTE = 'VieTech đã ghi nhận khoản thanh toán của đơn hàng này. Vui lòng liên hệ VieTech để được hỗ trợ hoàn tiền.'
  const THANKS = 'VieTech đã nhận được thanh toán cho đơn hàng này. Cảm ơn bạn!'

  test('a cancelled order still Paid says the money is recorded and points to the shop, without thanks or a refund claim', async () => {
    const server = mockApi({ 'GET /orders/o1': { body: { ...ORDER, OrderStatus: 'Cancelled', PaymentStatus: 'Paid',
      CancelReason: 'Hết hạn thanh toán QR (15 phút)' } } })
    renderAt('/don-hang/o1')

    expect(await screen.findByText('Đơn hàng đã bị huỷ. Lý do: Hết hạn thanh toán QR (15 phút)')).toBeInTheDocument()
    expect(screen.getByText(PAID_NOTE)).toBeInTheDocument()
    expect(screen.queryByText(THANKS)).not.toBeInTheDocument()
    expect(screen.queryByText(/Đã hoàn tiền|đã được hoàn/)).not.toBeInTheDocument()
    expect(summaryValue('Trạng thái thanh toán')).toHaveTextContent('Đã ghi nhận thanh toán')
    expect(screen.queryByRole('button', { name: 'Huỷ đơn hàng' })).not.toBeInTheDocument()
    // Nothing is written: no QR, no cancel, no refund call.
    expect(server.calls.filter((call) => call.method !== 'GET')).toEqual([])
  })

  test.each([
    ['Pending', 'Paid', true, false, 'Đã thanh toán'],
    ['Completed', 'Paid', true, false, 'Đã thanh toán'],
    ['Cancelled', 'Cancelled', false, false, 'Đã huỷ thanh toán'],
    ['Cancelled', 'Refunded', false, false, 'Đã hoàn tiền'],
  ])('other statuses are shown as before: %s / %s', async (orderStatus, paymentStatus, thanks, note, label) => {
    mockApi({ 'GET /orders/o1': { body: { ...ORDER, OrderStatus: orderStatus, PaymentStatus: paymentStatus } } })
    renderAt('/don-hang/o1')
    await vi.waitFor(() => expect(summaryValue('Trạng thái thanh toán')).toHaveTextContent(label))
    expect(Boolean(screen.queryByText(THANKS))).toBe(thanks)
    expect(Boolean(screen.queryByText(PAID_NOTE))).toBe(note)
    expect(Boolean(screen.queryByText('Đơn hàng đã bị huỷ.'))).toBe(orderStatus === 'Cancelled')
  })
})

describe('order page: outcome and details', () => {
  test('a transfer order just placed is called created and waiting for payment, never a success', async () => {
    mockApi()
    renderAt('/don-hang/o1', { state: { order: ORDER, paymentCode: 'SEPAY' } })

    expect(screen.getByRole('heading', { level: 1, name: 'Đã tạo đơn hàng, chờ thanh toán' })).toBeInTheDocument()
    expect(await screen.findByText('VTPAY12345678')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Đã tạo đơn hàng, chờ thanh toán' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /thành công/ })).not.toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Quét mã QR để thanh toán' })).getByText('Chờ thanh toán')).toBeInTheDocument()
  })

  test('only the server saying Paid makes it a payment success, with a way to the order details', async () => {
    const server = mockApi({ 'GET /orders/o1': { body: PAID } })
    const user = userEvent.setup()
    renderAt('/don-hang/o1', { state: { order: ORDER, paymentCode: 'SEPAY' } })

    expect(await screen.findByRole('heading', { level: 1, name: 'Thanh toán thành công' })).toBeInTheDocument()
    const success = screen.getByText('VieTech đã nhận được thanh toán cho đơn hàng này. Cảm ơn bạn!').closest('.order-success')
    await user.click(within(success).getByRole('button', { name: 'Xem chi tiết đơn hàng' }))
    expect(screen.getByRole('region', { name: 'Thông tin đơn hàng' })).toBeInTheDocument()
    expect(server.qrRequests()).toHaveLength(0)
  })

  test('the account name, account number and amount can be copied; checking the payment reads the order at once', async () => {
    const server = mockApi({ 'POST /orders/o1/payments/qr': { status: 201, body: { ...QR, AccountName: 'CONG TY VIETECH' } } })
    const user = userEvent.setup()
    renderAt('/don-hang/o1')
    const qr = await screen.findByRole('region', { name: 'Quét mã QR để thanh toán' })
    expect(within(qr).getByText('CONG TY VIETECH')).toBeInTheDocument()

    await user.click(within(qr).getByRole('button', { name: 'Sao chép số tài khoản 0123456789' }))
    expect(await navigator.clipboard.readText()).toBe('0123456789')
    expect(within(qr).getByText('Đã sao chép số tài khoản.')).toBeInTheDocument()
    await user.click(within(qr).getByRole('button', { name: 'Sao chép số tiền cần chuyển' }))
    expect(await navigator.clipboard.readText()).toBe('313334')
    expect(within(qr).getByText('Đã sao chép số tiền.')).toBeInTheDocument()

    const before = server.reads()
    await user.click(within(qr).getByRole('button', { name: 'Kiểm tra thanh toán' }))
    await vi.waitFor(() => expect(server.reads()).toBe(before + 1))
    expect(server.qrRequests()).toHaveLength(1)
  })

  test('without an account number there is nothing to copy and no account name is made up', async () => {
    mockApi({ 'POST /orders/o1/payments/qr': { status: 201, body: { ...QR, AccountNumber: null } } })
    renderAt('/don-hang/o1')
    const qr = await screen.findByRole('region', { name: 'Quét mã QR để thanh toán' })
    expect(within(qr).queryByRole('button', { name: /Sao chép số tài khoản/ })).not.toBeInTheDocument()
    expect(within(qr).queryByText('Chủ tài khoản')).not.toBeInTheDocument()
  })

  test('the order details show the lines, the amounts that make up the total and the delivery, as the server sent them', async () => {
    const item = { OrderItemId: 'i1', ProductVariantId: 'v1', ProductName: 'Laptop VieTech Pro 14', Sku: 'LT-14',
      VariantInfo: 'Màu: Bạc', WarrantyMonths: 12, Quantity: 2, UnitPrice: '166666.50', DiscountAmount: '49999.00', LineTotal: '283334.00' }
    mockApi({ 'GET /orders/o1': { body: { ...COD_ORDER, Items: [item], CustomerNote: 'Giao giờ hành chính' } } })
    renderAt('/don-hang/o1')

    const details = await screen.findByRole('region', { name: 'Thông tin đơn hàng' })
    const line = within(within(details).getByRole('list', { name: 'Sản phẩm trong đơn hàng' })).getByRole('listitem')
    expect(line).toHaveTextContent('Laptop VieTech Pro 14')
    expect(line).toHaveTextContent('Màu: Bạc')
    expect(line).toHaveTextContent('x2')
    expect(line).toHaveTextContent(vnd(283334))
    const value = (label) => within(details).getByText(label).nextElementSibling
    expect(value('Tạm tính')).toHaveTextContent(vnd(333333))
    expect(value('Phí vận chuyển')).toHaveTextContent(vnd(30000))
    expect(value('Giảm giá')).toHaveTextContent(`−${vnd(49999)}`)
    expect(value('Tổng cộng')).toHaveTextContent(vnd(313334))
    expect(value('Người nhận')).toHaveTextContent('Nguyễn Văn B · 0987654321')
    expect(value('Địa chỉ giao hàng')).toHaveTextContent(ORDER.ShippingAddress)
    expect(value('Ghi chú')).toHaveTextContent('Giao giờ hành chính')
  })
})

describe('order page: access', () => {
  test('an order of someone else is not shown', async () => {
    mockApi({ '/orders/x': { status: 404, body: { detail: 'Không tìm thấy đơn hàng', code: 'order_not_found' } } })
    renderAt('/don-hang/x')
    expect(await screen.findByRole('heading', { name: 'Không thể tải đơn hàng' })).toBeInTheDocument()
    expect(screen.getByText('Không tìm thấy đơn hàng')).toBeInTheDocument()
  })

  test('guests sign in first', async () => {
    const server = mockApi()
    const { router } = renderAt('/don-hang/o1', { auth: makeAuth() })
    await vi.waitFor(() => expect(router.state.location.pathname).toBe('/dang-nhap'))
    expect(router.state.location.search).toBe('?next=%2Fdon-hang%2Fo1')
    expect(server.calls.some((call) => call.endpoint.startsWith('/orders'))).toBe(false)
  })
})
