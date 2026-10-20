// @vitest-environment node
import { describe, expect, test } from 'vitest'
import { AuthApiError } from '../../../lib/auth-api.js'
import { ApiError, errorFromResponse } from '../../../services/api/client.js'
import { orderFailure } from './orderErrors.js'

// An ApiError as request() builds it from a backend answer.
const answer = (status, body) => errorFromResponse(status, body)
const VARIANT_ID = '3f2b9c1e-8d4a-4f6b-9e2c-7a1d5b0c9e88'
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-/i

describe('order rejected by the server: nothing was created', () => {
  test.each([
    [400, 'cart_empty', 'Giỏ hàng chưa có sản phẩm được chọn', 'cart', 'reloadCart'],
    [400, 'variant_not_available', `Sản phẩm không còn bán: ['${VARIANT_ID}']`, 'cart', 'reloadCart'],
    [400, 'insufficient_stock', `Không đủ tồn kho: ['${VARIANT_ID}']`, 'cart', 'reloadCart'],
    [400, 'order_total_zero', 'Đơn hàng 0 đồng không thể thanh toán chuyển khoản.', 'payment', 'edit'],
    [404, 'shipping_method_not_available', 'Phương thức vận chuyển không hợp lệ', 'shipping', 'reloadShipping'],
    [404, 'payment_method_not_available', 'Phương thức thanh toán không hợp lệ', 'payment', 'reloadPayment'],
    [404, 'address_not_found', 'Không tìm thấy địa chỉ', 'address', 'reloadAddresses'],
    [400, 'receiver_conflict', 'Chỉ chọn địa chỉ đã lưu hoặc nhập thông tin người nhận, không dùng cả hai', 'address', 'edit'],
    [404, 'user_not_found', 'Không tìm thấy tài khoản', 'summary', 'signIn'],
  ])('%i %s → %s / %s', (status, code, detail, place, action) => {
    const result = orderFailure(answer(status, { detail, code }))
    expect(result).toMatchObject({ outcome: 'rejected', place, action })
    expect(result.message).not.toBe('')
    expect(result.message).not.toMatch(UUID)
  })

  test('stock and withdrawn-product errors never show the variant ids of the server detail', () => {
    for (const code of ['variant_not_available', 'insufficient_stock']) {
      const { message } = orderFailure(answer(400, { detail: `Lỗi: ['${VARIANT_ID}']`, code }))
      expect(message).not.toContain(VARIANT_ID)
      expect(message).toMatch(/giỏ hàng/)
    }
  })

  test('zero-total transfer orders point to COD or removing the coupon', () => {
    expect(orderFailure(answer(400, { detail: 'x', code: 'order_total_zero' })).message).toMatch(/COD.*bỏ mã giảm giá/)
  })

  test.each([
    ['coupon_invalid', 'Mã giảm giá không hợp lệ'],
    ['coupon_expired', 'Mã giảm giá không còn hiệu lực'],
    ['coupon_usage_exceeded', 'Mã giảm giá đã hết lượt sử dụng'],
    ['coupon_min_order_value', 'Đơn hàng chưa đạt giá trị tối thiểu của mã giảm giá'],
    ['coupon_not_applicable', 'Mã giảm giá không áp dụng cho sản phẩm trong đơn'],
  ])('%s keeps the coupon verdict and asks for a new coupon check', (code, detail) => {
    expect(orderFailure(answer(400, { detail, code }))).toEqual({
      outcome: 'rejected', place: 'coupon', action: 'recheckCoupon', message: `${detail} Hãy bỏ mã hoặc quay lại giỏ hàng để đổi mã.`,
    })
  })

  test('an unknown business error gets a neutral message, never its detail', () => {
    const result = orderFailure(answer(409, { detail: `Dữ liệu đã tồn tại ${VARIANT_ID}`, code: 'duplicate_value' }))
    expect(result).toMatchObject({ outcome: 'rejected', place: 'summary', action: 'retry' })
    expect(result.message).not.toContain(VARIANT_ID)
    expect(orderFailure(answer(400, { detail: 'Internal stuff', code: 'something_new' }))).toMatchObject({ outcome: 'rejected', action: 'retry' })
    expect(orderFailure(answer(404, { detail: 'Not Found' })).message).toBe('Chưa đặt được hàng. Vui lòng kiểm tra lại thông tin rồi thử lại.')
  })
})

describe('sign-in and permission errors', () => {
  test('a 401 answered by the server means the order was not processed: sign in again', () => {
    for (const body of [{ detail: 'Cần đăng nhập để thực hiện thao tác này', code: 'authentication_required' }, { detail: 'Phiên đăng nhập không hợp lệ' }]) {
      expect(orderFailure(answer(401, body))).toMatchObject({ outcome: 'rejected', place: 'summary', action: 'signIn' })
    }
  })

  test('a 401 raised by withAccessToken itself (session changed while waiting) leaves the order unknown', () => {
    const result = orderFailure(new AuthApiError('Phiên đăng nhập đã thay đổi. Vui lòng thử lại.', 401))
    expect(result).toMatchObject({ outcome: 'unknown', place: 'summary', action: 'signIn' })
    expect(result.message).toMatch(/chưa xác định được đơn hàng đã được tạo hay chưa/)
  })

  test('403 (a Staff/Admin session, or a session of the other portal) asks for a customer account', () => {
    expect(orderFailure(answer(403, { detail: 'Bạn không có quyền thực hiện thao tác này', code: 'permission_denied' })))
      .toMatchObject({ outcome: 'rejected', action: 'signIn', message: expect.stringMatching(/tài khoản khách hàng/) })
    expect(orderFailure(new AuthApiError('Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.', 403))).toMatchObject({ outcome: 'rejected', action: 'signIn' })
  })
})

describe('422: FastAPI detail arrays', () => {
  test.each([
    [['body', 'ReceiverPhone'], 'String should have at most 20 characters', 'string_too_long', 'address'],
    [['body', 'ShippingAddress'], 'String should have at most 500 characters', 'string_too_long', 'address'],
    [['body', 'ShippingMethodId'], 'Input should be a valid UUID', 'uuid_parsing', 'shipping'],
    [['body', 'PaymentMethodId'], 'Field required', 'missing', 'payment'],
    [['body', 'CouponCode'], 'String should have at most 50 characters', 'string_too_long', 'coupon'],
    [['body'], 'Value error, Cần AddressId hoặc đủ ReceiverName, ReceiverPhone, ShippingAddress', 'value_error', 'summary'],
    [['body', 'Items'], 'Extra inputs are not permitted', 'extra_forbidden', 'summary'],
  ])('%j → %s', (loc, msg, type, place) => {
    const failure = answer(422, { detail: [{ loc, msg, type }] })
    expect(failure.detail).toBeNull()
    const result = orderFailure(failure)
    expect(result).toMatchObject({ outcome: 'rejected', place, action: 'edit' })
    // Field names and framework texts stay internal.
    expect(result.message).not.toMatch(/AddressId|Receiver|ShippingAddress|MethodId|CouponCode|Items|UUID|Field required/)
  })

  test('the first field with a known place wins; an empty list falls back to the summary', () => {
    const failure = answer(422, { detail: [
      { loc: ['body', 'Unknown'], msg: 'x', type: 'value_error' },
      { loc: ['body', 'PaymentMethodId'], msg: 'Input should be a valid UUID', type: 'uuid_parsing' },
      { loc: ['body', 'ReceiverName'], msg: 'Field required', type: 'missing' },
    ] })
    expect(orderFailure(failure).place).toBe('payment')
    expect(orderFailure(answer(422, { detail: [] })).place).toBe('summary')
    expect(orderFailure(answer(422, { detail: 'Không hợp lệ' })).place).toBe('summary')
  })
})

describe('lost answers: the order may have been created and is not sent again', () => {
  const lost = [
    ['a network failure', new ApiError('Không kết nối được máy chủ. Vui lòng kiểm tra kết nối và thử lại.')],
    ['a timeout', new DOMException('signal timed out', 'TimeoutError')],
    ['an aborted request', new DOMException('The operation was aborted.', 'AbortError')],
    ['500', answer(500, { detail: 'Internal Server Error' })],
    ['502 from a proxy', answer(502, null)],
    ['503 database error', answer(503, { detail: 'Không thể xử lý dữ liệu lúc này. Vui lòng thử lại' })],
    ['504', answer(504, null)],
    ['a 201 with an unreadable body', new ApiError('Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại.', 201)],
    ['a programming error', new TypeError('Cannot read properties of undefined')],
    ['a thrown string', 'boom'],
    ['nothing', undefined],
  ]

  test.each(lost)('%s → unknown, check the order first', (_name, failure) => {
    const result = orderFailure(failure)
    expect(result).toMatchObject({ outcome: 'unknown', place: 'summary', action: 'checkOrder' })
    expect(result.message).toMatch(/chưa xác định được đơn hàng đã được tạo hay chưa/)
    expect(result.message).toMatch(/kiểm tra đơn hàng/)
    expect(result.message).not.toMatch(/undefined|Internal|TypeError|signal/)
  })

  test('no unknown outcome is ever offered as a plain retry', () => {
    const failures = [...lost.map(([, failure]) => failure), new AuthApiError('Phiên đăng nhập đã thay đổi. Vui lòng thử lại.', 401)]
    for (const failure of failures) expect(orderFailure(failure).action).not.toBe('retry')
  })
})
