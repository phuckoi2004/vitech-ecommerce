import { request } from '../services/api/client.js'

// Orders and payments of the signed-in customer (docs/api-endpoints.md, "Đơn hàng và vận chuyển" and "Thanh toán và
// hoàn tiền"). Call through withAccessToken; business errors keep the server `code` (ApiError). Amounts are strings
// ("130000.00").

// POST /orders → 201 OrderDetailResponse (OrderId, OrderCode, TotalAmount, OrderStatus, PaymentStatus, Items, ...).
// `payload` is an OrderCreate, sent as given (build it with orderPayload): ShippingMethodId, PaymentMethodId, then
// AddressId or ReceiverName + ReceiverPhone + ShippingAddress, and optionally CouponCode, CustomerNote. The server
// orders the selected cart lines at its own prices; no line or price is sent. No payment is started here.
export function createOrder(accessToken, payload) {
  return request('/orders', { method: 'POST', body: payload, accessToken })
}

// PageResponse[CustomerOrderSummary] ({Items, Total, Page, PageSize}) of the customer's orders, newest first
// (OrderedAt); each order has Items ({OrderItemId, ProductName, VariantInfo, Quantity, ProductSlug}).
// `query`: page, page_size, order_code, order_status (one value or an array: any of them), ordered_from, ordered_to
// (with a time zone; the range is [from, to)).
export function listMyOrders(accessToken, query = {}, { signal } = {}) {
  return request('/orders', { query, accessToken, signal })
}

export function getOrder(accessToken, orderId, { signal } = {}) {
  return request(`/orders/${encodeURIComponent(orderId)}`, { accessToken, signal })
}

// Only a Pending order can be cancelled (order_not_cancellable). The body is required: {} or {CancelReason}.
export function cancelOrder(accessToken, orderId, payload = {}) {
  return request(`/orders/${encodeURIComponent(orderId)}/cancel`, { method: 'POST', body: payload, accessToken })
}

// POST /orders/{id}/payments/qr, without a body → 201 QrPaymentResponse (QrData, TransferContent, Bank, AccountNumber,
// TransferAmount, ExpiresAt, ...). Asking again returns the same pending QR. Only the verified webhook marks the order
// Paid, so the client reads PaymentStatus from getOrder to know it was paid.
export function createQrPayment(accessToken, orderId) {
  return request(`/orders/${encodeURIComponent(orderId)}/payments/qr`, { method: 'POST', accessToken })
}

// PaymentTransactionResponse[] of the customer's own order.
export function listOrderPayments(accessToken, orderId, { signal } = {}) {
  return request(`/orders/${encodeURIComponent(orderId)}/payments`, { accessToken, signal })
}

// Cancels a pending QR payment (payment_not_pending otherwise); no body.
export function cancelQrPayment(accessToken, paymentTransactionId) {
  return request(`/payments/${encodeURIComponent(paymentTransactionId)}/cancel`, { method: 'POST', accessToken })
}
