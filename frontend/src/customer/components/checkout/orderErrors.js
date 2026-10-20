import { ApiError } from '../../../services/api/client.js'

// What the order confirmation page shows and does when placing the order fails. `failure` is what createOrder
// (lib/order-api.js) rejected with through withAccessToken. Codes: backend/app/services/order.py create_order and
// promotion.py _evaluate; HTTP statuses: app/routers/errors.py. Returns {outcome, place, action, message}:
// - outcome: 'rejected' when the server refused the order: nothing was created, since a failed use case is rolled back
//   as a whole. 'unknown' when the answer was lost and the order may exist: it is never sent again on its own, the
//   customer checks the order first.
// - place: a field of the page ('address', 'shipping', 'payment', as in its data-field), the applied coupon
//   ('coupon'), the cart lines ('cart') or the summary next to the confirm button ('summary').
// - action: reloadCart, recheckCoupon, reloadAddresses, reloadShipping, reloadPayment, edit (change the form), signIn,
//   retry (send the same order again) or checkOrder.
// - message: Vietnamese text for the customer. Server details are not shown (some list variant ids), except the
//   coupon verdicts, which the coupon check already shows.

const CHECK_FIRST = 'Vui lòng kiểm tra đơn hàng của bạn trước khi đặt lại để tránh đặt trùng.'
const notKnown = (cause) => `${cause} nên chưa xác định được đơn hàng đã được tạo hay chưa. ${CHECK_FIRST}`
const COUPON_HINT = 'Hãy bỏ mã hoặc quay lại giỏ hàng để đổi mã.'

const BY_CODE = {
  cart_empty: ['cart', 'reloadCart',
    'Giỏ hàng không còn sản phẩm nào được chọn để đặt. Nếu bạn vừa đặt hàng, hãy kiểm tra đơn hàng trước khi đặt lại.'],
  variant_not_available: ['cart', 'reloadCart', 'Có sản phẩm trong đơn đã ngừng bán. Vui lòng cập nhật giỏ hàng rồi đặt lại.'],
  insufficient_stock: ['cart', 'reloadCart', 'Có sản phẩm không còn đủ số lượng trong kho. Vui lòng cập nhật giỏ hàng rồi đặt lại.'],
  order_total_zero: ['payment', 'edit',
    'Đơn hàng 0 đồng không thể thanh toán chuyển khoản. Vui lòng chọn thanh toán khi nhận hàng (COD) hoặc bỏ mã giảm giá.'],
  shipping_method_not_available: ['shipping', 'reloadShipping',
    'Phương thức vận chuyển đã chọn hiện không còn khả dụng. Vui lòng chọn phương thức khác.'],
  payment_method_not_available: ['payment', 'reloadPayment',
    'Phương thức thanh toán đã chọn hiện không còn khả dụng. Vui lòng chọn phương thức khác.'],
  address_not_found: ['address', 'reloadAddresses', 'Địa chỉ đã chọn không còn trong sổ địa chỉ. Vui lòng chọn hoặc nhập địa chỉ khác.'],
  receiver_conflict: ['address', 'edit', 'Thông tin nhận hàng chưa hợp lệ. Vui lòng chọn lại địa chỉ nhận hàng.'],
  user_not_found: ['summary', 'signIn', 'Không tìm thấy tài khoản của bạn. Vui lòng đăng nhập lại.'],
}

// OrderCreate fields of a 422 (ApiError.fieldErrors keys) and the place they belong to.
const FIELD_PLACES = {
  AddressId: 'address', ReceiverName: 'address', ReceiverPhone: 'address', ShippingAddress: 'address',
  ShippingMethodId: 'shipping', PaymentMethodId: 'payment', CouponCode: 'coupon',
}
const INVALID = {
  address: 'Thông tin nhận hàng chưa hợp lệ. Vui lòng kiểm tra lại họ tên, số điện thoại và địa chỉ.',
  shipping: 'Phương thức vận chuyển chưa hợp lệ. Vui lòng chọn lại.',
  payment: 'Phương thức thanh toán chưa hợp lệ. Vui lòng chọn lại.',
  coupon: `Mã giảm giá chưa hợp lệ. ${COUPON_HINT}`,
  summary: 'Thông tin đặt hàng chưa hợp lệ. Vui lòng kiểm tra lại rồi thử lại.',
}

const rejected = (place, action, message) => ({ outcome: 'rejected', place, action, message })
const unknown = (message, action = 'checkOrder') => ({ outcome: 'unknown', place: 'summary', action, message })

export function orderFailure(failure) {
  if (failure?.name === 'TimeoutError') return unknown(notKnown('Máy chủ phản hồi quá lâu'))
  if (failure?.name === 'AbortError') return unknown(notKnown('Yêu cầu đặt hàng bị ngắt giữa chừng'))
  if (!(failure instanceof ApiError)) return unknown(notKnown('Đã có lỗi xảy ra'))
  const { status, code } = failure
  if (status === 0) return unknown(notKnown('Không nhận được phản hồi từ máy chủ'))
  // A success whose body could not be read: the order was most likely created.
  if (status >= 200 && status < 300) return unknown(notKnown('Không đọc được phản hồi của máy chủ'))
  // Also proxies (502/504) and errors after the order was saved: the server may have placed it.
  if (status >= 500) return unknown(notKnown('Hệ thống gặp sự cố khi xử lý'))
  if (code && Object.hasOwn(BY_CODE, code)) return rejected(...BY_CODE[code])
  if (code?.startsWith('coupon_')) return rejected('coupon', 'recheckCoupon', `${failure.message} ${COUPON_HINT}`)
  if (status === 401) {
    // Without a server body the 401 comes from withAccessToken itself: the session changed or ended, possibly after
    // the order was placed and its answer discarded.
    if (code === null && failure.detail === null) {
      return unknown('Phiên đăng nhập vừa thay đổi nên chưa xác định được đơn hàng đã được tạo hay chưa. '
        + 'Vui lòng đăng nhập lại và kiểm tra đơn hàng của bạn trước khi đặt lại.', 'signIn')
    }
    return rejected('summary', 'signIn', 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để đặt hàng.')
  }
  if (status === 403) {
    return rejected('summary', 'signIn', 'Tài khoản hiện tại không thể đặt hàng. Vui lòng đăng nhập bằng tài khoản khách hàng.')
  }
  if (status === 422) {
    const place = Object.keys(failure.fieldErrors ?? {}).map((key) => FIELD_PLACES[key.split('.')[0]]).find(Boolean) ?? 'summary'
    return rejected(place, 'edit', INVALID[place])
  }
  return rejected('summary', 'retry', 'Chưa đặt được hàng. Vui lòng kiểm tra lại thông tin rồi thử lại.')
}
