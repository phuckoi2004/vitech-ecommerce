import { useState } from 'react'
import useApiData from '../../../hooks/useApiData.js'
import { previewCartCoupon } from '../../../lib/cart-api.js'

const STORAGE_PREFIX = 'vietech-cart-coupon:'

// 400 answers of GET /cart/coupon-preview that mean the code does not apply to these lines
// (backend/app/services/promotion.py _evaluate and preview_cart_coupon). Anything else is not a verdict on the code.
const REJECTIONS = new Set([
  'coupon_invalid', 'coupon_expired', 'coupon_usage_exceeded', 'coupon_min_order_value', 'coupon_not_applicable', 'cart_empty',
])

// The coupon code a customer applied in the cart, kept for this browser tab. The cart and the order confirmation
// page both read it when they open, and either page can remove it.
export function readCartCoupon(userId) {
  try {
    return sessionStorage.getItem(`${STORAGE_PREFIX}${userId}`) || ''
  } catch {
    return ''
  }
}

function saveCartCoupon(userId, code) {
  try {
    if (code) sessionStorage.setItem(`${STORAGE_PREFIX}${userId}`, code)
    else sessionStorage.removeItem(`${STORAGE_PREFIX}${userId}`)
  } catch { /* storage unavailable: the code still applies on this page */ }
}

// Forgets the code once an order has used it, so the next cart starts without one.
export function clearCartCoupon(userId) {
  saveCartCoupon(userId, '')
}

// The discount depends on the selected lines that can be bought, so it is checked again whenever they change.
function couponKey(code, cart) {
  if (!code || !cart?.Items.length) return null
  const basis = cart.Items.filter((line) => line.IsSelected && line.IsAvailable)
    .map((line) => `${line.CartItemId}:${line.Quantity}:${line.CurrentPrice}`).join('|')
  return `coupon:${code.toUpperCase()}:${basis}`
}

// Coupon applied to the cart, checked with the preview API each time a page opens and whenever the selected lines
// change. `status`:
// - none: no code; idle: a code but no cart lines to check it against;
// - checking; ok (with `preview`);
// - invalid: the server rejected the code for these lines (`error` is its message);
// - unavailable: the code could not be checked (network or server error, `error`); `retry()` asks again;
// - mismatch: the preview priced other lines than the cart on screen (it changed in between); reload the cart.
// `apply(preview)` takes a preview the dialog has just checked against this cart, so it is not requested again.
export default function useCartCoupon({ userId, cart, withAccessToken }) {
  const [code, setCode] = useState(() => readCartCoupon(userId))
  const [seed, setSeed] = useState(null)
  const key = couponKey(code, cart)
  const seeded = seed !== null && seed.key === key
  const check = useApiData(seeded ? null : key, async (signal) => {
    try {
      return { preview: await withAccessToken((token) => previewCartCoupon(token, code, { signal })) }
    } catch (failure) {
      if (failure?.status === 400 && REJECTIONS.has(failure.code)) return { rejected: failure.message }
      throw failure
    }
  })

  function apply(preview) {
    setCode(preview.Code)
    setSeed({ key: couponKey(preview.Code, cart), preview })
    saveCartCoupon(userId, preview.Code)
  }

  function remove() {
    setCode('')
    setSeed(null)
    saveCartCoupon(userId, '')
  }

  const result = seeded ? { preview: seed.preview } : check.data
  let status = 'checking'
  if (!code) status = 'none'
  else if (key === null) status = 'idle'
  else if (result?.rejected) status = 'invalid'
  else if (result?.preview) status = Number(result.preview.Subtotal) === Number(cart.SelectedSubtotal) ? 'ok' : 'mismatch'
  else if (check.error) status = 'unavailable'
  const error = status === 'invalid' ? result.rejected : status === 'unavailable' ? check.error : ''
  return { code, status, preview: status === 'ok' ? result.preview : null, error, retry: check.reload, apply, remove }
}
