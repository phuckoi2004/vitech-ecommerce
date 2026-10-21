import { variantImages } from '../../../lib/product-detail.js'

// Below this stock the line says how many are left instead of "Còn hàng".
export const LOW_STOCK = 5

// Whether a cart line (CartLineResponse) can be bought. `detail` is the public product detail: undefined while it
// loads or after a failed request, null when the product is no longer on sale (404). The public detail only lists
// variants on sale, so a missing variant means that variant was withdrawn.
// - ok / atLimit: buyable; atLimit means the quantity already equals the stock;
// - overStock: on sale but the quantity is above the current stock;
// - soldOut: no stock left; stopped: the product or variant is no longer sold.
export function lineStatus(line, detail) {
  const withdrawn = detail === null
    || (detail !== undefined && !(detail.Variants ?? []).some((variant) => variant.ProductVariantId === line.ProductVariantId))
  if (!line.IsAvailable) {
    if (withdrawn || line.Quantity <= line.StockQuantity) return 'stopped'
    return line.StockQuantity === 0 ? 'soldOut' : 'overStock'
  }
  return line.Quantity >= line.StockQuantity ? 'atLimit' : 'ok'
}

// What the line shows from its product detail: the photo of the colour in the cart (not the default variant's),
// link and "Xám • 256GB" (the variant name when the detail has no colour or storage, or is not available).
export function lineDisplay(line, detail) {
  const variant = detail?.Variants?.find((item) => item.ProductVariantId === line.ProductVariantId)
  const label = [variant?.Color, variant?.Storage].filter(Boolean).join(' • ')
  const imageUrl = detail ? variantImages(detail, line.ProductVariantId)[0]?.ImageUrl ?? null : null
  return { imageUrl, slug: detail?.Slug ?? null, variantLabel: label || line.VariantName }
}

const cents = (value) => Math.round(Number(value ?? 0) * 100)

// Amount due, as the order API computes TotalAmount: subtotal − discount + shipping fee
// (backend/app/services/order.py create_order). Worked in whole cents; amounts may be API strings ("30000.00").
export function orderTotal({ subtotal, discount = 0, shippingFee = 0 }) {
  return (cents(subtotal) - cents(discount) + cents(shippingFee)) / 100
}

// Why the applied coupon stops the order ('' when it does not); `changeHint` says where the code can be changed.
// An order with a code that does not apply is rejected as a whole, and an unchecked code has no known discount.
export function couponBlock(coupon, changeHint) {
  if (coupon.status === 'invalid') return `Mã giảm giá ${coupon.code} không dùng được. ${changeHint}`
  if (coupon.status === 'unavailable') return 'Chưa kiểm tra được mã giảm giá. Hãy thử lại hoặc bỏ mã.'
  if (coupon.status === 'mismatch') return 'Giỏ hàng vừa thay đổi. Hãy tải lại để cập nhật giảm giá.'
  return ''
}

// Why the selected lines cannot be ordered yet ('' when they can). The order API rejects the whole order when one
// selected line is not buyable, although the cart total silently leaves such lines out.
export function checkoutBlock(lines) {
  const selected = lines.filter((line) => line.IsSelected)
  if (!selected.length) return 'Hãy chọn ít nhất một sản phẩm để mua hàng.'
  if (selected.some((line) => !line.IsAvailable)) {
    return 'Có sản phẩm đã chọn không thể mua. Hãy cập nhật số lượng, bỏ chọn hoặc xóa sản phẩm đó.'
  }
  return ''
}
