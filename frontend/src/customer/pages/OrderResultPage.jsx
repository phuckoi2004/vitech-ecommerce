import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import Money from '../../components/shared/Money.jsx'
import useApiData from '../../hooks/useApiData.js'
import { listPaymentMethods, listShippingMethods } from '../../lib/catalog-api.js'
import CancelOrder from '../components/order/CancelOrder.jsx'
import { OrderItems, OrderPayment, OrderProgress, OrderRecipient, OrderShipping, OrderStatusLog, OrderTotals } from '../components/order/OrderDetails.jsx'
import { canCancel, cancelNote, statusHint } from '../components/order/orderDetail.js'
import { awaitingTransfer, orderTitle, POLL_MS, qrProblem } from '../components/order/orderPayment.js'
import QrPayment from '../components/order/QrPayment.jsx'
import useOrder from '../components/order/useOrder.js'
import useQrPayment from '../components/order/useQrPayment.js'
import { ACCOUNT_PATH, CHAT_PATH, ORDER_HISTORY_PATH } from '../routes/paths.js'
import './OrderResultPage.css'

// A placed order of the signed-in customer (Figma "Chi tiết đơn hàng"; also step 3 of the order flow), inside
// CustomerLayout and RequireCustomer. The order is always read from the server (GET /orders/{id}); the order passed by the confirmation
// page (`location.state`) is only shown until then. Its payment method is told by the Code of its PaymentMethodId in
// the payment methods list ('COD'); the Code passed by the confirmation page only fills in for a method missing from it.
// - COD: statuses and the amount to pay on delivery.
// - Transfer: the pending SePay QR (asking again returns the same QR), read again every POLL_MS until the server says
//   Paid, the order is cancelled or the QR deadline passes. Only the server's PaymentStatus says it is paid; until
//   then the title says the order waits for payment (orderTitle), never that it succeeded.
// A Pending order that is not paid can be cancelled. Progress, lines, amounts, delivery, payment and the status
// history follow, then the ways to get help.
export default function OrderResultPage() {
  const { orderId } = useParams()
  const location = useLocation()
  const placed = location.state?.order?.OrderId === orderId ? location.state : null
  const loaded = useOrder(orderId)
  const order = loaded.order ?? placed?.order ?? null
  const methods = useApiData('payment-methods', (signal) => listPaymentMethods({ signal }))
  const shippingMethods = useApiData('shipping-methods', (signal) => listShippingMethods({ signal }))
  const method = order ? methods.data?.find((item) => item.PaymentMethodId === order.PaymentMethodId) : undefined
  // The passed Code only once the list has answered without this method (e.g. a method withdrawn since).
  const code = method?.Code ?? (methods.loading ? null : placed?.paymentCode ?? null)
  const cod = code === 'COD'
  const transfer = code !== null && !cod
  const awaiting = Boolean(order) && transfer && awaitingTransfer(order)

  const qr = useQrPayment(orderId, awaiting)
  const problem = qr.failure ? qrProblem(qr.failure) : null
  const [now, setNow] = useState(() => Date.now())
  const deadline = qr.qr?.ExpiresAt ? Date.parse(qr.qr.ExpiresAt) : null
  const expired = awaiting && ((deadline !== null && now >= deadline) || Boolean(problem?.expired))
  const polling = awaiting && Boolean(qr.qr) && !expired
  const { read, reads } = loaded
  // The Code passed by the confirmation page only fills in the title while the methods list loads.
  const title = orderTitle(order, { code: code ?? placed?.paymentCode ?? null, placed: Boolean(placed) })
  const paid = Boolean(order) && order.PaymentStatus === 'Paid' && order.OrderStatus !== 'Cancelled'

  useEffect(() => {
    document.title = order ? `Đơn hàng ${order.OrderCode} | VieTech` : 'Đơn hàng | VieTech'
  }, [order])

  // The next read POLL_MS after the previous answer; stopped (and the request aborted) when polling ends or on leaving.
  // Coming back to the page (from the banking app or another tab) reads at once: browsers pause or slow the timers of
  // hidden pages. Still one request at a time: the waiting timer is replaced, not doubled.
  useEffect(() => {
    if (!polling) return undefined
    const controller = new AbortController()
    let timer = setTimeout(() => {
      timer = null
      void read(controller.signal)
    }, POLL_MS)
    function readOnReturn() {
      if (document.visibilityState !== 'visible' || timer === null) return
      clearTimeout(timer)
      timer = null
      void read(controller.signal)
    }
    document.addEventListener('visibilitychange', readOnReturn)
    return () => {
      document.removeEventListener('visibilitychange', readOnReturn)
      clearTimeout(timer)
      controller.abort()
    }
  }, [polling, reads, read])

  // The countdown to the QR deadline.
  const counting = awaiting && deadline !== null && !expired
  useEffect(() => {
    if (!counting) return undefined
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [counting])

  // Once more when the deadline passes (a payment of the last seconds), or when the QR answer says the order changed.
  const readOnce = expired || Boolean(problem?.refresh)
  useEffect(() => {
    if (!readOnce) return undefined
    const controller = new AbortController()
    void read(controller.signal)
    return () => controller.abort()
  }, [readOnce, read])

  if (!order) return <div className="shop-container od-page">
    <OrderPageHeading title={title} />
    {loaded.loading ? <LoadingState label="Đang tải đơn hàng…" />
      : <ErrorState title="Không thể tải đơn hàng" message={loaded.error} onRetry={loaded.refresh} />}
  </div>

  const methodName = method?.Name ?? (cod ? 'Thanh toán khi nhận hàng (COD)' : code ? 'Chuyển khoản' : 'Chưa xác định')
  const shippingName = shippingMethods.data?.find((item) => item.ShippingMethodId === order.ShippingMethodId)?.Name
    ?? (shippingMethods.loading ? 'Đang tải…' : 'Chưa xác định')
  const cancelled = order.OrderStatus === 'Cancelled'
  const payOnDelivery = cod && !cancelled && order.PaymentStatus === 'Pending'

  return <div className="shop-container od-page">
    <OrderPageHeading title={title} />
    {loaded.error && <p className="od-note" role="status">
      Chưa cập nhật được trạng thái mới nhất của đơn hàng.{polling ? ' Đang thử lại…' : ''}
    </p>}
    {paid && <div className="order-success" role="status">
      <span className="order-success-icon" aria-hidden="true">✓</span>
      <div className="order-success-body">
        <p>VieTech đã nhận được thanh toán cho đơn hàng này. Cảm ơn bạn!</p>
        <button type="button" className="order-link-button"
          onClick={() => document.getElementById('order-details')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })}>
          Xem chi tiết đơn hàng
        </button>
      </div>
    </div>}

    <OrderProgress order={order} methodLabel={cod ? 'COD' : code ? 'Chuyển khoản' : 'Chưa xác định'}>
      {cancelled ? <div className="od-hint is-cancelled" role="status">
        <p>Đơn hàng đã bị huỷ.{order.CancelReason ? ` Lý do: ${order.CancelReason}` : ''}</p>
        {/* Cancelled after the money came in (or cancelled once paid): the refund is a manual step at the shop. */}
        {order.PaymentStatus === 'Paid' && <p>
          VieTech đã ghi nhận khoản thanh toán của đơn hàng này. Vui lòng liên hệ VieTech để được hỗ trợ hoàn tiền.
        </p>}
      </div>
        : <div className="od-hint">
          <p>{awaiting ? 'Đơn hàng đang chờ thanh toán chuyển khoản. Vui lòng quét mã QR bên dưới để thanh toán.'
            : payOnDelivery && order.OrderStatus === 'Pending'
              ? <>Bạn sẽ thanh toán <Money value={order.TotalAmount} /> khi nhận hàng. VieTech sẽ liên hệ để xác nhận đơn hàng.</>
              : statusHint(order.OrderStatus)}</p>
        </div>}
    </OrderProgress>

    {awaiting && (expired ? <div className="order-panel is-expired" role="status">
      <p>{problem?.expired ? problem.message
        : 'Đã hết thời gian thanh toán. Đơn hàng sẽ được huỷ tự động; nếu bạn đã chuyển khoản, vui lòng liên hệ VieTech để được hỗ trợ.'}</p>
      <button type="button" className="order-link-button" onClick={loaded.refresh}>Kiểm tra lại trạng thái</button>
    </div>
      : qr.qr ? <QrPayment qr={qr.qr} now={now} onCheck={loaded.refresh} />
        : problem ? <div className="order-panel is-problem">
          <p role="alert">{problem.message}</p>
          {problem.retry && <button type="button" className="order-link-button" onClick={qr.retry}>Thử lại</button>}
        </div>
          : <LoadingState label="Đang tạo mã QR thanh toán…" />)}

    <section id="order-details" className="od-columns" aria-label="Thông tin đơn hàng">
      <div className="od-column">
        <OrderItems order={order} />
        <OrderTotals order={order} />
      </div>
      <div className="od-column">
        <OrderRecipient order={order} />
        <OrderShipping order={order} methodName={shippingName} />
        <OrderPayment order={order} methodName={methodName} cod={cod}>
          {payOnDelivery && <p className="od-muted">Thanh toán <Money value={order.TotalAmount} /> khi nhận hàng.</p>}
          {awaiting && !expired && <p className="od-muted">Quét mã QR ở trên để chuyển khoản <Money value={order.TotalAmount} />.</p>}
          {!code && !methods.loading && <p className="od-muted">
            Không xác định được phương thức thanh toán của đơn hàng.
            {methods.error && <> {methods.error} <button type="button" className="order-link-button" onClick={methods.reload}>Thử lại</button></>}
          </p>}
        </OrderPayment>
      </div>
    </section>

    <OrderStatusLog order={order} />

    <section className="od-card od-help" aria-labelledby="od-help-title">
      <div className="od-help-text">
        <h2 id="od-help-title">Cần hỗ trợ về đơn hàng?</h2>
        <p>{cancelNote(order)}</p>
      </div>
      <div className="od-help-actions">
        {canCancel(order) ? <CancelOrder order={order} transfer={transfer} onCancelled={loaded.replace} onStale={loaded.refresh} />
          : !cancelled && <button type="button" className="od-button is-muted" disabled>Hủy đơn</button>}
        <Link className="od-button is-outline" to={CHAT_PATH}>Chat hỗ trợ</Link>
        <Link className="od-button" to={ORDER_HISTORY_PATH}>Về lịch sử mua hàng</Link>
      </div>
    </section>
  </div>
}

// Breadcrumb and title, also shown while the order loads. `title` comes from orderTitle (placed / paid / details).
function OrderPageHeading({ title }) {
  return <>
    <nav className="od-breadcrumb" aria-label="Đường dẫn">
      <ol>
        <li><Link to={ACCOUNT_PATH}>Tài khoản</Link></li>
        <li><Link to={ORDER_HISTORY_PATH}>Lịch sử mua hàng</Link></li>
        <li aria-current="page">Chi tiết đơn hàng</li>
      </ol>
    </nav>
    <header className="od-heading">
      <div>
        <h1>{title}</h1>
        <p>Xem thông tin và tiến trình xử lý đơn hàng của bạn</p>
      </div>
      <Link className="od-button is-outline" to={ORDER_HISTORY_PATH}>← Lịch sử mua hàng</Link>
    </header>
  </>
}
