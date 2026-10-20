import { Link } from 'react-router-dom'
import couponIcon from '../../../assets/icons/coupon.svg'
import Money from '../../../components/shared/Money.jsx'
import { CHECKOUT_PATH } from '../../routes/paths.js'
import { orderTotal } from './cartLines.js'
import CouponProblem from './CouponProblem.jsx'

const BENEFITS = ['Sản phẩm chính hãng', 'Giao hàng nhanh', 'Hỗ trợ đổi trả và bảo hành']

// Figma "Order Summary". Amounts come from the server: SelectedSubtotal (selected lines that can be bought) and the
// coupon preview's DiscountAmount. `coupon` comes from useCartCoupon; `block` explains why the order cannot be placed
// yet; `pending` is true while a change or a coupon check is running. While a code could not be checked (or was
// checked against other lines) the total is unknown and is not shown.
export default function CartSummary({ cart, coupon, block, pending = false, onChooseCoupon, onRemoveCoupon, onRetryCoupon,
  onReloadCart }) {
  const selected = cart.Items.filter((line) => line.IsSelected).length
  const total = orderTotal({ subtotal: cart.SelectedSubtotal, discount: coupon.preview?.DiscountAmount })
  const unknown = coupon.status === 'unavailable' || coupon.status === 'mismatch'

  return <aside className="cart-summary" aria-labelledby="cart-summary-title">
    <h2 id="cart-summary-title" className="cart-summary-title">Thông tin đơn hàng</h2>
    <div>
      <div className={`cart-coupon-row${coupon.status === 'invalid' || unknown ? ' is-invalid' : ''}`}>
        <span className="cart-coupon-label">
          <img src={couponIcon} alt="" width="20" height="20" />
          {coupon.code ? <span>Mã giảm giá: <strong>{coupon.code}</strong></span> : 'Áp dụng mã giảm giá'}
        </span>
        <button type="button" className="cart-coupon-choose" aria-haspopup="dialog" disabled={pending}
          aria-label={coupon.code ? 'Đổi mã giảm giá' : 'Chọn mã giảm giá'} onClick={onChooseCoupon}>
          {coupon.code ? 'Đổi' : 'Chọn'}
        </button>
      </div>
      <CouponProblem coupon={coupon} className="cart-coupon-problem" onRetry={onRetryCoupon} onReload={onReloadCart}
        onRemove={onRemoveCoupon} />
    </div>
    <dl className="cart-summary-rows">
      <div><dt>Sản phẩm đã chọn</dt><dd>{selected} / {cart.Items.length}</dd></div>
      <div><dt>Tổng tiền hàng</dt><dd><Money value={cart.SelectedSubtotal} /></dd></div>
      {(coupon.status === 'ok' || coupon.status === 'checking') && <div>
        <dt>Giảm giá</dt>
        <dd className={coupon.preview ? 'is-discount' : 'is-muted'}>
          {coupon.preview ? <>−<Money value={coupon.preview.DiscountAmount} /></> : 'Đang kiểm tra…'}
        </dd>
      </div>}
    </dl>
    <p className="cart-summary-total">
      <span>Tạm tính</span>
      {coupon.status === 'checking' ? <span className="is-muted">Đang tính…</span>
        : unknown ? <span className="is-muted">Chưa xác định</span> : <Money value={total} />}
    </p>
    {coupon.preview && <p className="cart-summary-note">Mã giảm giá sẽ được kiểm tra lại khi bạn đặt hàng.</p>}
    {block || pending
      ? <button type="button" className="cart-summary-cta" disabled aria-describedby={block ? 'cart-checkout-block' : undefined}>
        Mua hàng
      </button>
      : <Link className="cart-summary-cta" to={CHECKOUT_PATH}>Mua hàng</Link>}
    {block && <p id="cart-checkout-block" className="cart-summary-block">{block}</p>}
    <p className="cart-summary-note">Bạn có thể xem lại sản phẩm, địa chỉ giao hàng và ghi chú ở bước xác nhận đặt hàng.</p>
    <ul className="cart-summary-benefits">
      {BENEFITS.map((text) => <li key={text}><span aria-hidden="true">✓ </span>{text}</li>)}
    </ul>
  </aside>
}
