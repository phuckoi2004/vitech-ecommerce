// What the customer order page (Figma "Chi tiết đơn hàng") says about an order's progress: the 4 steps, the colour of
// a status, the sentence for each status and the status history. OrderStatus values: backend app/schemas/common.py.
import { formatStatus } from '../../../lib/status-labels.js'
import { ORDER_STATUS } from './orderPayment.js'

export const ORDER_STEPS = [
  { label: 'Chờ xác nhận', statuses: ['Pending'] },
  { label: 'Đang xử lý', statuses: ['Confirmed', 'Processing'] },
  { label: 'Đang giao', statuses: ['Shipping'] },
  { label: 'Đã giao', statuses: ['Delivered', 'Completed'] },
]

// The 1-based step an order is at; 0 for a cancelled (or unknown) order, which shows no steps.
export function orderStep(status) {
  return ORDER_STEPS.findIndex((step) => step.statuses.includes(status)) + 1
}

const TONES = {
  Pending: 'waiting', Confirmed: 'progress', Processing: 'progress', Shipping: 'progress', Delivered: 'done', Completed: 'done',
  Cancelled: 'cancelled',
}
export const statusTone = (status) => TONES[status] ?? 'neutral'

const PAYMENT_TONES = { Pending: 'waiting', Paid: 'done', Failed: 'cancelled' }
export const paymentTone = (order) => (order.OrderStatus === 'Cancelled' && order.PaymentStatus !== 'Paid'
  ? 'neutral' : PAYMENT_TONES[order.PaymentStatus] ?? 'neutral')

const HINTS = {
  Pending: 'Đơn hàng đang chờ xác nhận. VieTech sẽ liên hệ để xác nhận đơn hàng.',
  Confirmed: 'VieTech đã xác nhận đơn hàng và đang chuẩn bị hàng cho bạn.',
  Processing: 'Đơn hàng đang được đóng gói để bàn giao cho đơn vị vận chuyển.',
  Shipping: 'Đơn hàng đang trên đường giao. Bạn có thể xem thông tin vận chuyển và liên hệ hỗ trợ khi cần.',
  Delivered: 'Đơn hàng đã được giao thành công. Hãy đánh giá sản phẩm để giúp những khách hàng khác.',
  Completed: 'Đơn hàng đã hoàn tất. Cảm ơn bạn đã mua sắm tại VieTech, hãy đánh giá sản phẩm bạn đã nhận nhé.',
}
export const statusHint = (status) => HINTS[status] ?? ''

const EVENTS = {
  Pending: 'Hệ thống tiếp nhận đơn hàng thành công.',
  Confirmed: 'VieTech đã xác nhận đơn hàng.',
  Processing: 'Đơn hàng đang được chuẩn bị và đóng gói.',
  Shipping: 'Đơn hàng đã được bàn giao cho đơn vị vận chuyển.',
  Delivered: 'Đơn hàng đã được giao đến bạn.',
  Completed: 'Đơn hàng đã hoàn tất.',
  Cancelled: 'Đơn hàng đã được huỷ.',
}

// StatusHistories newest first; a note written with the change replaces the usual sentence.
export function historyEntries(histories = []) {
  return [...histories]
    .sort((a, b) => Date.parse(b.ChangedAt) - Date.parse(a.ChangedAt))
    .map((entry) => ({
      id: entry.OrderStatusHistoryId,
      status: entry.NewStatus,
      text: entry.Note?.trim() || EVENTS[entry.NewStatus] || '',
      at: entry.ChangedAt,
    }))
}

// Only a Pending order that is not paid can be cancelled by its customer (OrderService.cancel_customer_order).
export const canCancel = (order) => order.OrderStatus === 'Pending' && order.PaymentStatus !== 'Paid'

// Under "Cần hỗ trợ về đơn hàng?": whether the customer can cancel, and why not.
export function cancelNote(order) {
  if (order.SourceReturnRequestId) {
    return order.PaymentStatus === 'Paid'
      ? 'Đơn đổi đã chốt nên không thể hủy phiếu. Vui lòng chat với VieTech nếu cần hỗ trợ.'
      : order.OrderStatus === 'Cancelled'
        ? 'Đơn đổi đã hủy. Xem phiếu đổi trả để theo dõi tiến trình.'
        : 'Bạn có thể hủy phiếu trước khi chốt đơn đổi. Hủy phiếu sẽ hủy cả đơn đổi và giải phóng hàng đang giữ.'
  }
  if (order.OrderStatus === 'Cancelled') return 'Đơn hàng đã được huỷ. Bạn có thể chat với VieTech nếu cần hỗ trợ thêm.'
  if (order.OrderStatus !== 'Pending') {
    return `Đơn ${formatStatus(order.OrderStatus, ORDER_STATUS).toLowerCase()}, nên chức năng hủy đơn không khả dụng ở trạng thái này.`
  }
  if (order.PaymentStatus === 'Paid') return 'Đơn hàng đã được thanh toán nên không thể tự huỷ. Vui lòng chat với VieTech để được hỗ trợ.'
  return 'Bạn có thể huỷ đơn khi đơn hàng chưa được xác nhận.'
}
