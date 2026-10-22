import { useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import Money from '../../components/shared/Money.jsx'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { getProduct } from '../../lib/catalog-api.js'
import { createExchangeOrder } from '../../lib/return-api.js'
import { variantPrice } from '../../lib/product-detail.js'
import useExchange, { exchangePath } from '../hooks/useExchange.js'
import { orderPath, returnRequestPath, SEARCH_PATH } from '../routes/paths.js'

export default function ExchangeCheckout() {
  const exchange = useExchange()
  const [params] = useSearchParams()
  const { withAccessToken } = useCustomerSession()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const lock = useRef(false)
  const [receiver, setReceiver] = useState({ ReceiverName: '', ReceiverPhone: '', ShippingAddress: '' })
  const [changeAddress, setChangeAddress] = useState(false)
  const productId = params.get('product') || exchange.data?.OriginalProductId
  const product = useApiData(productId ? `exchange-product:${productId}` : null,
    (signal) => getProduct(productId, { signal }))
  const variantId = params.get('variant') || exchange.data?.OriginalVariantId
  const variant = product.data?.Variants?.find((row) => row.ProductVariantId === variantId)
  const price = variantPrice(variant)
  const credit = variantId === exchange.data?.OriginalVariantId ? price ?? 0 : Math.min(Number(exchange.data?.CreditLimit ?? 0), price ?? 0)
  const due = Math.max(0, (price ?? 0) - credit)

  async function place(event) {
    event.preventDefault()
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try {
      const order = await withAccessToken((token) => createExchangeOrder(token, exchange.id,
        { ProductVariantId: variantId, ...(changeAddress ? receiver : {}) }))
      navigate(orderPath(order.OrderId), { replace: true, state: { order } })
    } catch (failure) { setError(failure.message); exchange.reload(); product.reload() }
    finally { lock.current = false; setBusy(false) }
  }

  if (exchange.loading || product.loading) return <LoadingState label="Đang kiểm tra đơn đổi trả…" />
  if (exchange.error || product.error) return <ErrorState message={exchange.error || product.error} onRetry={() => { exchange.reload(); product.reload() }} />
  const context = exchange.data
  if (!context) return null
  if (context.OrderId) return <div className="checkout-page"><h1>Đơn đổi trả {context.OrderCode}</h1>
    <p>{context.Committed ? 'Đơn đã chốt.' : 'Đơn đang chờ thanh toán. Tiếp tục đơn này để tránh tạo trùng.'}</p>
    <Link className="cw-primary" to={orderPath(context.OrderId)}>Xem đơn đổi trả</Link></div>
  if (!context.CanChoose) return <div className="checkout-page"><p>Phiếu chưa tiếp nhận hoặc đã đóng, chưa thể tạo đơn đổi.</p>
    <Link to={returnRequestPath(exchange.id)}>Quay lại phiếu</Link></div>
  const valid = variant && product.data.CategoryId === context.CategoryId && Number(variant.StockQuantity) > 0
    && (!context.OriginalInStock || variantId === context.OriginalVariantId)
  return <div className="checkout-page">
    <Link to={returnRequestPath(exchange.id)}>← Phiếu {context.RequestCode}</Link>
    <h1 className="checkout-title">Xác nhận đơn đổi trả</h1>
    <form className="checkout-card space-y-5" onSubmit={place}>
      <h2>{product.data?.Name} · {variant?.VariantName || variant?.Color}</h2>
      <label>Số lượng <input className="cacc-input" type="number" value="1" disabled /></label>
      <Link className="cw-text-link" to={exchangePath(SEARCH_PATH, exchange.id)}>Xóa sản phẩm / chọn lại</Link>
      {!valid && <p role="alert">Sản phẩm đã hết hàng, khác danh mục hoặc máy ban đầu đã có hàng trở lại. Hãy chọn lại.</p>}
      <p>Giao hàng tiêu chuẩn · Miễn phí</p>
      <label><input type="checkbox" checked={changeAddress} onChange={(e) => setChangeAddress(e.target.checked)} /> Đổi địa chỉ nhận hàng</label>
      {changeAddress ? Object.entries({ ReceiverName: 'Họ tên người nhận', ReceiverPhone: 'Số điện thoại', ShippingAddress: 'Địa chỉ giao hàng' }).map(([key, label]) =>
        <label className="block" key={key}>{label}<input className="cacc-input" required maxLength={key === 'ReceiverPhone' ? 20 : key === 'ReceiverName' ? 255 : 500}
          value={receiver[key]} onChange={(e) => setReceiver({ ...receiver, [key]: e.target.value })} /></label>)
        : <p>Giao đến người nhận và địa chỉ trong đơn mua ban đầu.</p>}
      <dl className="checkout-readonly">
        <div><dt>Giá máy mới sau khuyến mãi</dt><dd><Money value={price ?? 0} /></dd></div>
        <div><dt>Giá trị dùng đổi</dt><dd>−<Money value={credit} /></dd></div>
        <div><dt>Cần thanh toán</dt><dd><Money value={due} /></dd></div>
      </dl>
      <p>Đổi 1 máy. Phần giá trị còn dư không hoàn tiền và không giữ lại cho lần mua sau.</p>
      <p>{due > 0 ? 'Tạo đơn xong sẽ thanh toán phần bù bằng QR. Chỉ chốt khi hệ thống xác nhận đã nhận tiền.' : 'Đơn 0đ được chốt ngay, bỏ qua thanh toán và không thể hủy phiếu sau khi xác nhận.'}</p>
      {error && <p role="alert" className="text-red-600">{error}</p>}
      <button className="cw-primary" disabled={busy || !valid}>{busy ? 'Đang tạo đơn…' : due > 0 ? 'Tạo đơn và thanh toán phần bù' : 'Xác nhận đổi · 0đ'}</button>
    </form>
  </div>
}
