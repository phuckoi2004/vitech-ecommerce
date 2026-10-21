import { useEffect, useId, useRef, useState } from 'react'
import couponIcon from '../../../assets/icons/coupon.svg'
import Money from '../../../components/shared/Money.jsx'
import useApiData from '../../../hooks/useApiData.js'
import { previewCartCoupon } from '../../../lib/cart-api.js'
import { listCoupons } from '../../../lib/catalog-api.js'
import { formatDate, formatMoney } from '../../../lib/format.js'

// Figma "Mã giảm giá" (259:341). Under the code field, the public coupons (GET /coupons) to choose from. Choosing one,
// or "Áp dụng" on a typed code, checks it against the selected lines; "Xác nhận" applies it (checking it first if
// needed), or removes the current code when the field is empty. A coupon whose minimum order the selected lines do
// not reach says how much is missing and cannot be chosen. Closing does not change the cart.
// `code` is the code in use (if any); `applied` its preview while it is valid; `subtotal` the cart's SelectedSubtotal.
export default function CouponDialog({ code = '', applied = null, subtotal = 0, withAccessToken, onConfirm, onClose }) {
  const dialog = useRef(null)
  const field = useRef(null)
  const titleId = useId()
  const [draft, setDraft] = useState(code)
  const [checked, setChecked] = useState(applied)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const coupons = useApiData('public-coupons', (signal) => listCoupons({ signal }))
  const typed = draft.trim()
  const ready = checked !== null && checked.Code.toLowerCase() === typed.toLowerCase()

  useEffect(() => {
    dialog.current.showModal()
    // showModal() focuses the first button (close); start in the code field instead.
    field.current.focus()
  }, [])

  async function check(value = typed) {
    setPending(true); setError('')
    try {
      const preview = await withAccessToken((token) => previewCartCoupon(token, value))
      setChecked(preview)
      return preview
    } catch (failure) {
      setChecked(null)
      setError(failure.message)
      return null
    } finally {
      setPending(false)
    }
  }

  function pick(value) {
    setDraft(value)
    check(value)
  }

  async function confirm() {
    if (!typed) return onConfirm(null)
    const preview = ready ? checked : await check()
    if (preview) onConfirm(preview)
  }

  function close() {
    if (!pending) onClose()
  }

  return <dialog ref={dialog} className="cart-coupon-dialog" aria-labelledby={titleId}
    onCancel={(event) => { event.preventDefault(); close() }}
    onClick={(event) => { if (event.target === dialog.current) close() }}>
    <div className="cart-coupon-inner">
      <div className="cart-coupon-head">
        <h2 id={titleId}>Nhập hoặc chọn mã khuyến mãi</h2>
        <button type="button" className="cart-coupon-close" aria-label="Đóng" disabled={pending} onClick={close}>
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <form className="cart-coupon-field" onSubmit={(event) => { event.preventDefault(); if (typed && !pending) check() }}>
        <input ref={field} value={draft} placeholder="Nhập mã khuyến mãi" aria-label="Mã khuyến mãi" maxLength={50}
          autoComplete="off" autoCapitalize="characters" spellCheck={false}
          onChange={(event) => { setDraft(event.target.value); setError('') }} />
        <button type="submit" disabled={!typed || pending}>Áp dụng</button>
      </form>
      <div className="cart-coupon-status" aria-live="polite">
        {pending ? <p>Đang kiểm tra mã…</p>
          : error ? <p className="cart-coupon-error" role="alert">{error}</p>
            : ready ? <CouponResult preview={checked} /> : null}
      </div>
      <CouponList coupons={coupons} subtotal={subtotal} chosen={ready ? checked.Code : ''} disabled={pending}
        onPick={pick} />
      <div className="cart-coupon-foot">
        {code && <button type="button" className="cart-coupon-remove" disabled={pending} onClick={() => onConfirm(null)}>
          Bỏ mã đang dùng
        </button>}
        <button type="button" className="cart-coupon-confirm" disabled={pending} onClick={confirm}>Xác nhận</button>
      </div>
    </div>
  </dialog>
}

// The checked code: its discount on the selected lines (only part of them when the promotion is limited).
function CouponResult({ preview }) {
  const partial = Number(preview.EligibleSubtotal) < Number(preview.Subtotal)
  return <div className="cart-coupon-result">
    <img src={couponIcon} alt="" width="20" height="20" />
    <div>
      <p className="cart-coupon-code">{preview.Code}</p>
      <p>Giảm <Money value={preview.DiscountAmount} /> {partial
        ? <>cho các sản phẩm được áp dụng (<Money value={preview.EligibleSubtotal} />)</>
        : 'cho các sản phẩm đã chọn'}</p>
    </div>
  </div>
}

const discountText = (coupon) => coupon.DiscountType === 'Percentage'
  ? `Giảm ${Number(coupon.DiscountValue).toLocaleString('vi-VN')}%`
  : `Giảm ${formatMoney(coupon.DiscountValue)}`

function conditionText(coupon) {
  return [
    Number(coupon.MinOrderValue) > 0 ? `Đơn từ ${formatMoney(coupon.MinOrderValue)}` : 'Mọi đơn hàng',
    coupon.MaxDiscountAmount != null && `Giảm tối đa ${formatMoney(coupon.MaxDiscountAmount)}`,
    `HSD ${formatDate(coupon.EndDate)}`,
    coupon.RemainingUses != null && `Còn ${coupon.RemainingUses} lượt`,
  ].filter(Boolean).join(' · ')
}

// The public coupons in the order the API lists them (newest first). Whether a code applies to the selected lines
// (scope, uses left) is only known once it is checked; the minimum order is known here and shown before.
function CouponList({ coupons, subtotal, chosen, disabled, onPick }) {
  if (coupons.loading) return <p className="cart-coupon-note" role="status">Đang tải mã khuyến mãi…</p>
  if (coupons.error) return <p className="cart-coupon-note">
    Chưa tải được danh sách mã. <button type="button" className="cart-coupon-retry" onClick={coupons.reload}>Thử lại</button>
    <br />Bạn vẫn có thể nhập mã vào ô phía trên.
  </p>
  if (!coupons.data?.length) return <p className="cart-coupon-note">
    Hiện chưa có mã khuyến mãi nào để chọn.<br />Nhập mã bạn có vào ô phía trên để kiểm tra ưu đãi.
  </p>
  return <ul className="cart-coupon-list" aria-label="Mã khuyến mãi có thể chọn">
    {coupons.data.map((coupon) => {
      const missing = Number(coupon.MinOrderValue) - Number(subtotal)
      const selected = chosen.toLowerCase() === coupon.Code.toLowerCase()
      return <li key={coupon.CouponId} className={`cart-coupon-option${selected ? ' is-selected' : ''}${missing > 0 ? ' is-locked' : ''}`}>
        <span className="cart-coupon-value">{discountText(coupon)}</span>
        <div className="cart-coupon-info">
          <p className="cart-coupon-name">{coupon.Name}</p>
          <p className="cart-coupon-code">{coupon.Code}</p>
          <p>{conditionText(coupon)}</p>
          {missing > 0 && <p className="cart-coupon-missing">Mua thêm <Money value={missing} /> để dùng mã này</p>}
        </div>
        <button type="button" aria-label={`Chọn mã ${coupon.Code}`} aria-pressed={selected}
          disabled={disabled || missing > 0} onClick={() => onPick(coupon.Code)}>{selected ? 'Đã chọn' : 'Chọn'}</button>
      </li>
    })}
  </ul>
}
