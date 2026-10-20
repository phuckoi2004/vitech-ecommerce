import { Link } from 'react-router-dom'
import Money from '../../../components/shared/Money.jsx'
import { CART_PATH } from '../../routes/paths.js'
import { lineDisplay, orderTotal } from '../cart/cartLines.js'
import CouponProblem from '../cart/CouponProblem.jsx'
import StoreImage from '../StoreImage.jsx'

// Figma "Checkout Summary": the selected cart lines as the server priced them, then the amounts of the order API:
// subtotal (SelectedSubtotal) − discount (the coupon preview, checked again when this page opens) + the BaseFee of the
// chosen shipping method. The server prices the order again when it is placed. The code applied in the cart can only
// be removed here; it is changed in the cart. `coupon` comes from useCartCoupon; `block` explains why the order
// cannot be confirmed; `waiting` disables the button while data loads and `placing` while the order is being sent;
// `orderProblem` (OrderProblem) tells why the last attempt failed.
export default function CheckoutSummary({ cart, lines, details, shipping, coupon, block, orderProblem, waiting, placing,
  onRemoveCoupon, onRetryCoupon, onReload }) {
  const fee = shipping ? shipping.BaseFee : null
  const quantity = lines.reduce((sum, line) => sum + line.Quantity, 0)
  const unknown = coupon.status === 'unavailable' || coupon.status === 'mismatch'
  const problem = unknown || coupon.status === 'invalid'
  const total = orderTotal({ subtotal: cart.SelectedSubtotal, discount: coupon.preview?.DiscountAmount, shippingFee: fee ?? 0 })

  return <aside className="checkout-summary" aria-labelledby="checkout-summary-title">
    <h2 id="checkout-summary-title" className="checkout-summary-title">Đơn hàng của bạn</h2>
    <ul className="checkout-items">
      {lines.map((line) => <li key={line.CartItemId}><SummaryItem line={line} detail={details[line.ProductId]} /></li>)}
    </ul>
    <dl className="checkout-totals">
      <div><dt>Tạm tính ({quantity} sản phẩm)</dt><dd><Money value={cart.SelectedSubtotal} /></dd></div>
      {coupon.preview && <div>
        <dt>Giảm giá</dt>
        <dd className="is-discount">−<Money value={coupon.preview.DiscountAmount} /></dd>
      </div>}
      <div>
        <dt>Phí vận chuyển</dt>
        <dd>{fee === null ? <span className="is-muted">Chọn phương thức vận chuyển</span>
          : Number(fee) > 0 ? <Money value={fee} /> : 'Miễn phí'}</dd>
      </div>
      <div className="checkout-coupon">
        <dt>Mã giảm giá</dt>
        <dd>{!coupon.code ? 'Chưa áp dụng' : <>
          <strong>{coupon.code}</strong>
          {coupon.status === 'checking' && <span className="is-muted"> · Đang kiểm tra…</span>}
          {!problem && <button type="button" className="checkout-link" aria-label={`Bỏ mã giảm giá ${coupon.code}`}
            onClick={onRemoveCoupon}>Bỏ mã</button>}
        </>}</dd>
      </div>
    </dl>
    <CouponProblem coupon={coupon} className="checkout-coupon-problem" onRetry={onRetryCoupon} onReload={onReload}
      onRemove={onRemoveCoupon} />
    <p className="checkout-total">
      <span>Tổng thanh toán</span>
      {coupon.status === 'checking' ? <span className="is-muted">Đang tính…</span>
        : unknown ? <span className="is-muted">Chưa xác định</span> : <Money value={total} />}
    </p>
    <p className="checkout-note">Giá, tồn kho, phí vận chuyển và mã giảm giá được hệ thống kiểm tra lại khi tạo đơn hàng.</p>
    {orderProblem}
    <button type="submit" className="checkout-submit" disabled={waiting || placing || !!block}
      aria-describedby={block ? 'checkout-block' : undefined}>{placing ? 'Đang đặt hàng…' : 'Xác nhận đặt hàng'}</button>
    {block && <p id="checkout-block" className="checkout-block">{block}</p>}
    <Link className="checkout-back" to={CART_PATH}><span aria-hidden="true">←</span>Quay lại giỏ hàng</Link>
  </aside>
}

// Figma "Order Product": image, name, colour/storage and quantity, unit price × quantity and the line total.
function SummaryItem({ line, detail }) {
  const { imageUrl, variantLabel } = lineDisplay(line, detail)
  return <article className="checkout-item" aria-label={line.ProductName}>
    <div className="checkout-item-media" aria-hidden="true">
      <StoreImage src={imageUrl} alt="" loading="lazy" decoding="async" fallback={<span className="checkout-item-noimage">VieTech</span>} />
    </div>
    <div className="checkout-item-info">
      <h3 className="checkout-item-name">{line.ProductName}</h3>
      <p className="checkout-item-meta">{variantLabel} • SL: {line.Quantity}</p>
      <p className="checkout-item-meta">Đơn giá: <Money value={line.CurrentPrice} /></p>
      <p className="checkout-item-total"><Money value={line.LineTotal} /></p>
    </div>
  </article>
}
