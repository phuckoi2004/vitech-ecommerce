import { request } from '../services/api/client.js'

// Cart of the signed-in customer (docs/api-endpoints.md, "Yêu thích và giỏ hàng"). Every call returns the whole
// CartSummaryResponse, priced by the server from current prices and stock; the client never sends a price.

export function getCart(accessToken, { signal } = {}) {
  return request('/cart', { accessToken, signal })
}

// `changes`: {Quantity} and/or {IsSelected}. A quantity above the current stock is rejected (insufficient_stock).
export function updateCartItem(accessToken, cartItemId, changes) {
  return request(`/cart/items/${encodeURIComponent(cartItemId)}`, { method: 'PATCH', body: changes, accessToken })
}

// Selects or clears every line at once.
export function setCartSelection(accessToken, isSelected) {
  return request('/cart/selection', { method: 'PUT', body: { IsSelected: isSelected }, accessToken })
}

export function removeCartItem(accessToken, cartItemId) {
  return request(`/cart/items/${encodeURIComponent(cartItemId)}`, { method: 'DELETE', accessToken })
}

// {Code, PromotionId, Subtotal, EligibleSubtotal, DiscountAmount} for the selected lines that can be bought. The code
// is matched case-insensitively and nothing is reserved: placing the order checks it again. Business errors (400):
// coupon_invalid, coupon_expired, coupon_usage_exceeded, coupon_min_order_value, coupon_not_applicable, cart_empty.
export function previewCartCoupon(accessToken, code, { signal } = {}) {
  return request('/cart/coupon-preview', { query: { code }, accessToken, signal })
}
