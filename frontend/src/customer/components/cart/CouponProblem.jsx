const PROBLEMS = new Set(['invalid', 'unavailable', 'mismatch'])

// What is wrong with the applied coupon (useCartCoupon status invalid, unavailable or mismatch) and what the customer
// can do: try the check again, reload the cart, or go on without the code. Renders nothing for the other statuses.
// A failed check is never presented as a rejected code.
export default function CouponProblem({ coupon, className, onRetry, onReload, onRemove }) {
  if (!PROBLEMS.has(coupon.status)) return null
  return <div className={className} role="alert">
    <p>
      {coupon.status === 'invalid' && coupon.error}
      {coupon.status === 'unavailable' && `Chưa kiểm tra được mã giảm giá. ${coupon.error}`}
      {coupon.status === 'mismatch' && 'Giỏ hàng vừa thay đổi nên số tiền giảm chưa khớp. Hãy tải lại để cập nhật.'}
    </p>
    <div>
      {coupon.status === 'unavailable' && <button type="button" onClick={onRetry}>Thử lại</button>}
      {coupon.status === 'mismatch' && <button type="button" onClick={onReload}>Tải lại</button>}
      <button type="button" onClick={onRemove}>Bỏ mã</button>
    </div>
  </div>
}
