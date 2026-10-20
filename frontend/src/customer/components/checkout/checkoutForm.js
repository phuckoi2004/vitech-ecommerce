import { formatMoney } from '../../../lib/format.js'

// Column sizes of AddressCreate / OrderCreate (backend/app/schemas/user.py, order.py).
export const RECEIVER_LIMITS = { ReceiverName: 255, ReceiverPhone: 20, Province: 100, Ward: 100, DetailAddress: 255 }

// Vietnamese mobile or landline number in its 0… form, or null. Same rule as normalize_phone_number in
// backend/app/schemas/auth.py; the order API itself stores ReceiverPhone as given, so the page checks it.
export function normalizePhone(value) {
  let phone = value.replace(/[\s().-]/g, '')
  if (phone.startsWith('+84')) phone = `0${phone.slice(3)}`
  else if (phone.startsWith('0084')) phone = `0${phone.slice(4)}`
  return /^(?:0[35789]\d{8}|02\d{9})$/.test(phone) ? phone : null
}

// "Số 1 Đại Cồ Việt, Phường Bách Khoa, Hà Nội": the order API joins a saved address the same way.
export function addressLine({ DetailAddress, Ward, Province }) {
  return [DetailAddress, Ward, Province].map((part) => part?.trim()).filter(Boolean).join(', ')
}

// A new receiver starts from the customer's own name and phone.
export function newReceiver(user) {
  return { ReceiverName: user?.FullName ?? '', ReceiverPhone: user?.PhoneNumber ?? '', Province: '', Ward: '', DetailAddress: '' }
}

// "Dự kiến 3 ngày • 30.000 ₫" / "… • Miễn phí". The order is charged the method's BaseFee.
export function shippingDetail(method) {
  const fee = Number(method.BaseFee) > 0 ? formatMoney(method.BaseFee) : 'Miễn phí'
  const days = method.EstimatedDays > 0 ? `Dự kiến ${method.EstimatedDays} ngày` : 'Giao trong ngày'
  return `${days} • ${fee}`
}

// Errors by field, in the order the form shows them ({} when the order can be sent). `delivery` is
// {mode: 'saved', addressId} for an address-book entry or {mode: 'new', receiver} for one typed here.
export function validateCheckout({ delivery, shippingMethodId, paymentMethodId }) {
  const errors = {}
  if (delivery.mode === 'saved') {
    if (!delivery.addressId) errors.address = 'Vui lòng chọn địa chỉ nhận hàng.'
  } else {
    const receiver = delivery.receiver
    if (!receiver.ReceiverName.trim()) errors.ReceiverName = 'Vui lòng nhập họ tên người nhận.'
    if (!receiver.ReceiverPhone.trim()) errors.ReceiverPhone = 'Vui lòng nhập số điện thoại người nhận.'
    else if (!normalizePhone(receiver.ReceiverPhone)) {
      errors.ReceiverPhone = 'Số điện thoại không hợp lệ. Vui lòng nhập số Việt Nam, ví dụ 0912345678.'
    }
    if (!receiver.Province.trim()) errors.Province = 'Vui lòng nhập Tỉnh/Thành phố.'
    if (!receiver.Ward.trim()) errors.Ward = 'Vui lòng nhập Phường/Xã.'
    if (!receiver.DetailAddress.trim()) errors.DetailAddress = 'Vui lòng nhập địa chỉ chi tiết (số nhà, tên đường).'
  }
  if (!shippingMethodId) errors.shipping = 'Vui lòng chọn phương thức vận chuyển.'
  if (!paymentMethodId) errors.payment = 'Vui lòng chọn phương thức thanh toán.'
  return errors
}

// OrderCreate body for a valid form. Lines, prices, the shipping fee, the discount and totals are not sent: the server
// takes the selected cart lines, prices them and applies `couponCode` (the code of a coupon checked as ok) itself.
// Not sent from this page yet (placing orders is a later stage).
export function orderPayload({ delivery, shippingMethodId, paymentMethodId, note = '', couponCode = '' }) {
  const body = { ShippingMethodId: shippingMethodId, PaymentMethodId: paymentMethodId }
  if (delivery.mode === 'saved') {
    body.AddressId = delivery.addressId
  } else {
    const receiver = delivery.receiver
    body.ReceiverName = receiver.ReceiverName.trim()
    body.ReceiverPhone = normalizePhone(receiver.ReceiverPhone)
    body.ShippingAddress = addressLine(receiver)
  }
  if (note.trim()) body.CustomerNote = note.trim()
  if (couponCode) body.CouponCode = couponCode
  return body
}
