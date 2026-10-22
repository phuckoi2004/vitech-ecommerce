// Order and payment rules of the customer's order page, from the backend: OrderStatus/PaymentStatus values
// (app/schemas/common.py), when a QR can be had (PaymentService QR_PAYABLE_ORDER_STATUSES / _PAYMENT_STATUSES) and
// the errors of POST /orders/{id}/payments/qr (create_qr_payment, _ensure_qr_payable, the SePay gateway).

// The order is read again this often while it waits for its transfer.
import { formatStatus } from '../../../lib/status-labels.js'

export const POLL_MS = 3000

export const ORDER_STATUS = {
  Pending: 'Chờ xác nhận', Confirmed: 'Đã xác nhận', Processing: 'Đang xử lý', Shipping: 'Đang vận chuyển',
  Delivered: 'Đã giao hàng', Completed: 'Hoàn tất', Cancelled: 'Đã huỷ',
}
const PAYMENT_STATUS = {
  Paid: 'Đã thanh toán', Failed: 'Thanh toán không thành công', Refunded: 'Đã hoàn tiền', Cancelled: 'Đã huỷ thanh toán',
}

// "Đã thanh toán" only when the server says Paid (set by the verified payment webhook, or COD collected on delivery).
// A cancelled order still Paid holds money to give back: it reads as recorded, without saying it was refunded.
// An unpaid COD order is "Chưa thanh toán" (paid on delivery), a transfer order "Chờ thanh toán" (its QR).
export function paymentStatusText(order, cod) {
  if (order.SourceReturnRequestId && Number(order.TotalAmount) === 0) return 'Không cần thanh toán · Đã chốt đơn đổi'
  if (order.PaymentStatus === 'Pending') return cod ? 'Chưa thanh toán' : 'Chờ thanh toán'
  if (order.PaymentStatus === 'Paid' && order.OrderStatus === 'Cancelled') return 'Đã ghi nhận thanh toán'
  return formatStatus(order.PaymentStatus, PAYMENT_STATUS)
}

// The page title. A transfer order is "placed, waiting for payment" until the server says Paid, so "Đặt hàng thành
// công" is never shown for money that has not arrived; "Thanh toán thành công" only once PaymentStatus is Paid.
// `code` is the order's payment method Code (null while unknown), `placed` whether the confirmation page opened it.
export function orderTitle(order, { code, placed }) {
  if (order?.SourceReturnRequestId && Number(order.TotalAmount) === 0) return 'Đã chốt đơn đổi trả'
  if (!order || order.OrderStatus === 'Cancelled') return 'Chi tiết đơn hàng'
  const cod = code === 'COD'
  if (code && !cod && order.PaymentStatus === 'Paid') return 'Thanh toán thành công'
  if (!placed) return 'Chi tiết đơn hàng'
  return cod ? 'Đặt hàng thành công' : code ? 'Đã tạo đơn hàng, chờ thanh toán' : 'Đã tạo đơn hàng'
}

// A transfer order the backend still gives a QR for: not cancelled, shipped or paid.
export function awaitingTransfer(order) {
  if (order.SourceReturnRequestId && Number(order.TotalAmount) === 0) return false
  return ['Pending', 'Confirmed', 'Processing'].includes(order.OrderStatus) && ['Pending', 'Failed'].includes(order.PaymentStatus)
}

// "14:05" (minutes:seconds) left until `deadline` (ms since epoch), "00:00" once passed.
export function timeLeft(deadline, now) {
  const seconds = Math.max(0, Math.ceil((deadline - now) / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

const AGAIN = { retry: true }
const QR_PROBLEMS = {
  // The 15 minutes after the order passed: no QR, the order is cancelled by the expiry job.
  order_payment_expired: { expired: true, message: 'Đơn hàng đã hết thời gian thanh toán (15 phút) và sẽ được huỷ tự động.' },
  // Paid, cancelled or moved on meanwhile: the order is read again.
  order_not_payable: { refresh: true, message: 'Đơn hàng không còn chờ thanh toán chuyển khoản.' },
  payment_request_cancelled: { refresh: true, message: 'Đơn hàng không còn chờ thanh toán chuyển khoản.' },
  payment_method_is_cod: { refresh: true, message: 'Đơn hàng này thanh toán khi nhận hàng (COD), không cần chuyển khoản.' },
  order_total_zero: { message: 'Đơn hàng này không thể thanh toán chuyển khoản. Vui lòng liên hệ VieTech để được hỗ trợ.' },
  qr_amount_not_supported: { message: 'Đơn hàng này không thể thanh toán chuyển khoản. Vui lòng liên hệ VieTech để được hỗ trợ.' },
  order_not_found: { message: 'Không tìm thấy đơn hàng.' },
  payment_gateway_not_configured: { ...AGAIN,
    message: 'Thanh toán chuyển khoản hiện chưa sẵn sàng. Vui lòng thử lại sau hoặc huỷ đơn để đặt lại với hình thức khác.' },
  qr_payment_in_progress: { ...AGAIN, message: 'Mã QR đang được tạo. Vui lòng thử lại sau giây lát.' },
  qr_payment_unavailable: { ...AGAIN, message: 'Chưa tạo được mã QR. Vui lòng thử lại.' },
  payment_code_collision: { ...AGAIN, message: 'Chưa tạo được mã QR. Vui lòng thử lại.' },
}

// What the page shows and does when the QR request fails: {message, retry, refresh, expired}. Asking again is safe
// (the backend returns the pending QR instead of a new one), so unknown and network errors offer a retry. Server
// details are not shown.
export function qrProblem(failure) {
  const known = failure?.code && Object.hasOwn(QR_PROBLEMS, failure.code) ? QR_PROBLEMS[failure.code] : null
  return { retry: false, refresh: false, expired: false, message: 'Chưa lấy được mã QR thanh toán. Vui lòng thử lại.',
    ...(known ?? AGAIN) }
}
