// @vitest-environment node
import { afterEach, describe, expect, test, vi } from 'vitest'
import { ApiError } from '../services/api/client.js'
import { cancelOrder, cancelQrPayment, createOrder, createQrPayment, getOrder, listMyOrders, listOrderPayments } from './order-api.js'

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => vi.unstubAllGlobals())

// Records each call as {url, method, headers, body}; `reply` answers every call.
function mockFetch(reply) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    calls.push({ url, method: options.method, headers: options.headers, body: options.body, signal: options.signal })
    return typeof reply === 'function' ? reply() : reply
  }))
  return calls
}

const ORDER = {
  OrderId: 'o1', OrderCode: 'VT261015ABC123', TotalAmount: '313334.00', OrderStatus: 'Pending', PaymentStatus: 'Pending',
  OrderedAt: '2026-10-15T08:00:00Z', Subtotal: '333333.00', ShippingFee: '30000.00', DiscountAmount: '49999.00', Items: [],
}
const QR = {
  PaymentTransactionId: 't1', OrderId: 'o1', Amount: '313334.00', Status: 'Pending', QrData: 'https://qr.example/img?amount=313334',
  TransferContent: 'VTPAY12345678', Bank: 'Vietcombank', AccountNumber: '0123456789', TransferAmount: 313334,
  ExpiresAt: '2026-10-15T08:15:00Z',
}

describe('order API contracts', () => {
  test('createOrder posts the OrderCreate body unchanged, with bearer access, and returns the created order', async () => {
    const calls = mockFetch(json(ORDER, 201))
    const payload = { ShippingMethodId: 's1', PaymentMethodId: 'm1', AddressId: 'a2', CouponCode: 'GIAM15', CustomerNote: 'Gọi trước' }
    await expect(createOrder('access', payload)).resolves.toEqual(ORDER)
    expect(calls).toHaveLength(1)
    expect(calls[0]).toMatchObject({ url: '/api/orders', method: 'POST' })
    expect(calls[0].headers).toMatchObject({ Authorization: 'Bearer access', 'Content-Type': 'application/json' })
    // Exactly the fields given: no line, price, total or other field is added.
    expect(JSON.parse(calls[0].body)).toEqual(payload)
  })

  test('a receiver typed for this order is sent as its three fields', async () => {
    const calls = mockFetch(json(ORDER, 201))
    const payload = { ShippingMethodId: 's2', PaymentMethodId: 'm2', ReceiverName: 'Lê Văn D', ReceiverPhone: '0912345678',
      ShippingAddress: '1 Đại Cồ Việt, Phường Bách Khoa, Hà Nội' }
    await createOrder('access', payload)
    expect(JSON.parse(calls[0].body)).toEqual(payload)
  })

  test('getOrder and listOrderPayments are authenticated GETs without a body, and pass the abort signal', async () => {
    const calls = mockFetch(() => json(ORDER))
    const controller = new AbortController()
    await expect(getOrder('access', 'o/1', { signal: controller.signal })).resolves.toEqual(ORDER)
    await listOrderPayments('access', 'o/1', { signal: controller.signal })
    expect(calls.map((call) => call.url)).toEqual(['/api/orders/o%2F1', '/api/orders/o%2F1/payments'])
    for (const call of calls) {
      expect(call.method).toBe('GET')
      expect(call.body).toBeUndefined()
      expect(call.headers.Authorization).toBe('Bearer access')
      expect(call.signal).toBe(controller.signal)
    }
  })

  test('listMyOrders reads the customer order history with its paging query', async () => {
    const page = { Items: [ORDER], Total: 1, Page: 1, PageSize: 1 }
    const calls = mockFetch(() => json(page))
    await expect(listMyOrders('access', { page: 1, page_size: 1 })).resolves.toEqual(page)
    await listMyOrders('access')
    expect(calls.map((call) => [call.url, call.method, call.body])).toEqual([
      ['/api/orders?page=1&page_size=1', 'GET', undefined],
      ['/api/orders', 'GET', undefined],
    ])
    expect(calls[0].headers.Authorization).toBe('Bearer access')
  })

  test('cancelOrder always sends a body: {} by default, or the reason', async () => {
    const calls = mockFetch(() => json({ ...ORDER, OrderStatus: 'Cancelled' }))
    await expect(cancelOrder('access', 'o1')).resolves.toMatchObject({ OrderStatus: 'Cancelled' })
    await cancelOrder('access', 'o1', { CancelReason: 'Đổi ý' })
    expect(calls.map((call) => [call.url, call.method, call.body])).toEqual([
      ['/api/orders/o1/cancel', 'POST', '{}'],
      ['/api/orders/o1/cancel', 'POST', '{"CancelReason":"Đổi ý"}'],
    ])
    expect(calls[0].headers).toMatchObject({ Authorization: 'Bearer access', 'Content-Type': 'application/json' })
  })

  test('createQrPayment posts without any body and returns the transfer details as sent by the server', async () => {
    const calls = mockFetch(json(QR, 201))
    await expect(createQrPayment('access', 'o1')).resolves.toEqual(QR)
    expect(calls[0]).toMatchObject({ url: '/api/orders/o1/payments/qr', method: 'POST' })
    expect(calls[0].body).toBeUndefined()
    expect(calls[0].headers).not.toHaveProperty('Content-Type')
    expect(calls[0].headers.Authorization).toBe('Bearer access')
  })

  test('cancelQrPayment posts without any body', async () => {
    const calls = mockFetch(json({ ...QR, Status: 'Cancelled' }))
    await expect(cancelQrPayment('access', 't 1')).resolves.toMatchObject({ Status: 'Cancelled' })
    expect(calls[0]).toMatchObject({ url: '/api/payments/t%201/cancel', method: 'POST' })
    expect(calls[0].body).toBeUndefined()
    expect(calls[0].headers).not.toHaveProperty('Content-Type')
    expect(calls[0].headers.Authorization).toBe('Bearer access')
  })
})

describe('order API errors', () => {
  test.each([
    ['createOrder', () => createOrder('access', { ShippingMethodId: 's1', PaymentMethodId: 'm2', AddressId: 'a1' }), 400,
      'order_total_zero', 'Đơn hàng 0 đồng không thể thanh toán chuyển khoản.'],
    ['createOrder', () => createOrder('access', { ShippingMethodId: 's1', PaymentMethodId: 'm1', AddressId: 'a1' }), 400,
      'insufficient_stock', 'Không đủ tồn kho'],
    ['createOrder', () => createOrder('access', { ShippingMethodId: 's9', PaymentMethodId: 'm1', AddressId: 'a1' }), 404,
      'shipping_method_not_available', 'Phương thức vận chuyển không hợp lệ'],
    ['createQrPayment', () => createQrPayment('access', 'o1'), 409, 'qr_payment_in_progress', 'Yêu cầu thanh toán QR đang được xử lý'],
    ['createQrPayment', () => createQrPayment('access', 'o1'), 502, 'qr_payment_unavailable', 'Không tạo được yêu cầu thanh toán QR'],
    ['cancelOrder', () => cancelOrder('access', 'o1'), 400, 'order_not_cancellable', 'Không thể hủy đơn ở trạng thái Confirmed'],
    ['cancelQrPayment', () => cancelQrPayment('access', 't1'), 400, 'payment_not_pending', 'Giao dịch không ở trạng thái chờ thanh toán'],
  ])('%s rejects with the business error code (%i %s)', async (_name, call, status, code, detail) => {
    mockFetch(json({ detail, code }, status))
    const error = await call().catch((failure) => failure)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status, code, detail, message: detail })
  })

  test('a validation error of the order body keeps its field errors', async () => {
    mockFetch(json({ detail: [{ loc: ['body'], msg: 'Value error, Cần AddressId hoặc đủ ReceiverName, ReceiverPhone, ShippingAddress', type: 'value_error' }] }, 422))
    const error = await createOrder('access', { ShippingMethodId: 's1', PaymentMethodId: 'm1' }).catch((failure) => failure)
    expect(error).toMatchObject({ status: 422, code: null, message: 'Cần AddressId hoặc đủ ReceiverName, ReceiverPhone, ShippingAddress' })
  })

  test('an expired session rejects with 401 so withAccessToken can renew it', async () => {
    mockFetch(json({ detail: 'Cần đăng nhập để thực hiện thao tác này', code: 'authentication_required' }, 401))
    await expect(getOrder('expired', 'o1')).rejects.toMatchObject({ status: 401, code: 'authentication_required' })
  })

  test('a network failure while placing an order is an error, never a success, and the order is not sent twice', async () => {
    const fetch = vi.fn(async () => { throw new TypeError('Failed to fetch') })
    vi.stubGlobal('fetch', fetch)
    const error = await createOrder('access', { ShippingMethodId: 's1', PaymentMethodId: 'm1', AddressId: 'a1' }).catch((failure) => failure)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 0 })
    expect(error.message).toMatch(/Không kết nối được máy chủ/)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  test('a server error on the QR request is not retried and is not a success', async () => {
    const calls = mockFetch(json({ detail: 'Internal Server Error' }, 500))
    await expect(createQrPayment('access', 'o1')).rejects.toMatchObject({ status: 500, message: 'Hệ thống đang bận. Vui lòng thử lại sau.' })
    expect(calls).toHaveLength(1)
  })

  test('an aborted order read rejects instead of resolving', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn(async () => {
      controller.abort()
      throw new DOMException('Aborted', 'AbortError')
    }))
    await expect(getOrder('access', 'o1', { signal: controller.signal })).rejects.toThrow()
  })
})
