import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import useApiData from '../../hooks/useApiData.js'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { request } from '../../services/api/client.js'
import { formatMoney } from '../../lib/format.js'
import { canPurchase } from '../../lib/product-detail.js'
import './PublicCoupons.css'

export default function PublicCoupons({ productId, variant, compact = false }) {
  const list = useApiData(`public-coupons:${productId ?? 'all'}`, (signal) => request('/coupons', {
    query: { product_id: productId }, signal,
  }))
  const { reload } = list
  const send = useCustomerRequest()
  const { user } = useCustomerSession()
  const [message, setMessage] = useState('')
  const [quote, setQuote] = useState(null)
  const [busy, setBusy] = useState('')
  const pending = useRef(false)
  useEffect(() => {
    const timer = window.setInterval(reload, 30000)
    const focus = () => reload()
    window.addEventListener('focus', focus)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', focus) }
  }, [reload])

  async function copy(code) {
    try { await navigator.clipboard.writeText(code); setMessage(`Đã sao chép mã ${code}.`) }
    catch { setMessage(`Bạn có thể sao chép mã: ${code}`) }
  }

  async function preview(code) {
    if (pending.current || !canPurchase(variant)) return
    pending.current = true
    setBusy(code); setMessage(''); setQuote(null)
    try {
      const result = await (user ? send : request)('/pricing/quote', { method: 'POST', body: {
        Items: [{ ProductVariantId: variant.ProductVariantId, Quantity: 1 }], CouponCode: code,
      } })
      setQuote(result)
    } catch (error) { setMessage(error.message || 'Không thể xem thử mã giảm giá.') }
    finally { pending.current = false; setBusy('') }
  }

  return <section className={`public-coupons${compact ? ' is-compact' : ''}`} aria-label="Mã ưu đãi công khai">
    <header><div><h2>Mã ưu đãi dành cho bạn</h2><p>Không cần lưu mã. Mã có giới hạn lượt dùng, áp dụng theo điều kiện.</p></div>
      {!compact && <Link to="/tim-kiem">Khám phá sản phẩm →</Link>}
    </header>
    {list.loading ? <p role="status">Đang tải mã ưu đãi…</p> : list.error ? <p role="alert">{list.error} <button type="button" onClick={list.reload}>Thử lại</button></p>
      : !list.data?.length ? <p>Hiện chưa có mã ưu đãi còn lượt áp dụng{productId ? ' cho sản phẩm này' : ''}.</p>
        : <div className="public-coupon-grid">{list.data.map((coupon) => <article className="public-coupon" key={coupon.CouponId}>
          <div className="public-coupon-value">{coupon.DiscountType === 'Percentage'
            ? `Giảm ${Number(coupon.DiscountValue).toLocaleString('vi-VN')}%` : `Giảm ${formatMoney(coupon.DiscountValue)}`}</div>
          <div className="public-coupon-content"><h3>{coupon.Name}</h3><code>{coupon.Code}</code>
            <p>Đơn từ {formatMoney(coupon.MinOrderValue)} sau giảm trực tiếp{coupon.MaxDiscountAmount != null ? ` · Giảm tối đa ${formatMoney(coupon.MaxDiscountAmount)}` : ''}</p>
            <p>Hạn dùng {new Date(coupon.EndDate).toLocaleDateString('vi-VN')} · Mỗi tài khoản 1 lần</p>
            <p>{coupon.RemainingUses === null ? 'Không giới hạn tổng lượt' : `Còn ${coupon.RemainingUses} lượt sử dụng`}</p>
            <div className="public-coupon-actions"><button type="button" onClick={() => void copy(coupon.Code)}>Sao chép mã</button>
              {variant && <button type="button" disabled={!!busy || !canPurchase(variant)} onClick={() => void preview(coupon.Code)}>{busy === coupon.Code ? 'Đang tính…' : 'Xem thử giá sau mã'}</button>}
            </div>
          </div>
        </article>)}</div>}
    {message && <p className="public-coupon-message" role="status">{message}</p>}
    {quote && <div className="public-coupon-quote" role="status">
      <p>Mã <strong>{quote.CouponCode}</strong>: giảm thêm {formatMoney(quote.CouponDiscount)}</p>
      <p>Tiền hàng cho 1 sản phẩm: <strong>{formatMoney(quote.Total)}</strong></p>
      <p>Giá xem trước, chưa gồm phí vận chuyển. Chưa giữ lượt mã; điều kiện được kiểm tra lại khi đặt hàng.</p>
    </div>}
  </section>
}
