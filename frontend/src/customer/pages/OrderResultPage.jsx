import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { buttonClassName } from '../../components/shared/buttonStyles.js'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import Money from '../../components/shared/Money.jsx'
import useApiData from '../../hooks/useApiData.js'
import { listPaymentMethods } from '../../lib/catalog-api.js'
import CancelOrder from '../components/order/CancelOrder.jsx'
import { awaitingTransfer, ORDER_STATUS, paymentStatusText, POLL_MS, qrProblem } from '../components/order/orderPayment.js'
import QrPayment from '../components/order/QrPayment.jsx'
import useOrder from '../components/order/useOrder.js'
import useQrPayment from '../components/order/useQrPayment.js'
import { HOME_PATH } from '../routes/paths.js'
import './CheckoutPage.css'
import './OrderResultPage.css'

// A placed order of the signed-in customer (step 3 "Thanh toán / Hoàn tất"), inside CustomerLayout and
// RequireCustomer. The order is always read from the server (GET /orders/{id}); the order passed by the confirmation
// page (`location.state`) is only shown until then. Its payment method is told by the Code of its PaymentMethodId in
// the payment methods list ('COD'); the Code passed by the confirmation page only fills in for a method missing from it.
// - COD: statuses and the amount to pay on delivery.
// - Transfer: the pending SePay QR (asking again returns the same QR), read again every POLL_MS until the server says
//   Paid, the order is cancelled or the QR deadline passes. Only the server's PaymentStatus says it is paid.
// A Pending order that is not paid can be cancelled.
export default function OrderResultPage() {
  const { orderId } = useParams()
  const location = useLocation()
  const placed = location.state?.order?.OrderId === orderId ? location.state : null
  const loaded = useOrder(orderId)
  const order = loaded.order ?? placed?.order ?? null
  const methods = useApiData('payment-methods', (signal) => listPaymentMethods({ signal }))
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

  useEffect(() => {
    document.title = order ? `Đơn hàng ${order.OrderCode} | VieTech` : 'Đơn hàng | VieTech'
  }, [order])

  // The next read POLL_MS after the previous answer; stopped (and the request aborted) when polling ends or on leaving.
  useEffect(() => {
    if (!polling) return undefined
    const controller = new AbortController()
    const timer = setTimeout(() => void read(controller.signal), POLL_MS)
    return () => {
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

  return <div className="checkout-page">
    <div className="checkout-card">
      <nav className="checkout-breadcrumb" aria-label="Đường dẫn">
        <ol>
          <li><Link to={HOME_PATH}>Trang chủ</Link></li>
          <li aria-current="page">Đơn hàng{order ? ` ${order.OrderCode}` : ''}</li>
        </ol>
      </nav>
      <h1 className="checkout-title">{placed ? 'Đặt hàng thành công' : 'Chi tiết đơn hàng'}</h1>
      {!order ? loaded.loading ? <LoadingState label="Đang tải đơn hàng…" />
        : <ErrorState title="Không thể tải đơn hàng" message={loaded.error} onRetry={loaded.refresh} />
        : <>
          {loaded.error && <p className="order-note" role="status">
            Chưa cập nhật được trạng thái mới nhất của đơn hàng.{polling ? ' Đang thử lại…' : ''}
          </p>}
          <dl className="checkout-readonly order-summary">
            <div><dt>Mã đơn hàng</dt><dd>{order.OrderCode}</dd></div>
            <div><dt>Trạng thái đơn hàng</dt><dd>{ORDER_STATUS[order.OrderStatus] ?? order.OrderStatus}</dd></div>
            <div><dt>Tổng thanh toán</dt><dd><Money value={order.TotalAmount} /></dd></div>
            <div><dt>Phương thức thanh toán</dt><dd>{method?.Name ?? (cod ? 'Thanh toán khi nhận hàng (COD)' : code ? 'Chuyển khoản' : 'Chưa xác định')}</dd></div>
            <div><dt>Trạng thái thanh toán</dt><dd>{paymentStatusText(order, cod)}</dd></div>
          </dl>
          {order.PaymentStatus === 'Paid' && order.OrderStatus !== 'Cancelled' && <p className="order-banner is-success" role="status">
            VieTech đã nhận được thanh toán cho đơn hàng này. Cảm ơn bạn!
          </p>}
          {order.OrderStatus === 'Cancelled' && <div className="order-banner is-cancelled" role="status">
            <p>Đơn hàng đã bị huỷ.{order.CancelReason ? ` Lý do: ${order.CancelReason}` : ''}</p>
            {/* Cancelled after the money came in (or cancelled once paid): the refund is a manual step at the shop. */}
            {order.PaymentStatus === 'Paid' && <p>
              VieTech đã ghi nhận khoản thanh toán của đơn hàng này. Vui lòng liên hệ VieTech để được hỗ trợ hoàn tiền.
            </p>}
          </div>}
          {cod && order.OrderStatus !== 'Cancelled' && order.PaymentStatus === 'Pending' && <p className="order-note">
            Bạn sẽ thanh toán <Money value={order.TotalAmount} /> khi nhận hàng. VieTech sẽ liên hệ để xác nhận đơn hàng.
          </p>}
          {!code && !methods.loading && <p className="order-note">
            Không xác định được phương thức thanh toán của đơn hàng.
            {methods.error && <> {methods.error} <button type="button" className="order-link-button" onClick={methods.reload}>Thử lại</button></>}
          </p>}
          {awaiting && (expired ? <div className="order-panel is-expired" role="status">
            <p>{problem?.expired ? problem.message
              : 'Đã hết thời gian thanh toán. Đơn hàng sẽ được huỷ tự động; nếu bạn đã chuyển khoản, vui lòng liên hệ VieTech để được hỗ trợ.'}</p>
            <button type="button" className="order-link-button" onClick={loaded.refresh}>Kiểm tra lại trạng thái</button>
          </div>
            : qr.qr ? <QrPayment qr={qr.qr} now={now} />
              : problem ? <div className="order-panel is-problem">
                <p role="alert">{problem.message}</p>
                {problem.retry && <button type="button" className="order-link-button" onClick={qr.retry}>Thử lại</button>}
              </div>
                : <LoadingState label="Đang tạo mã QR thanh toán…" />)}
          {order.OrderStatus === 'Pending' && order.PaymentStatus !== 'Paid' && <CancelOrder order={order} transfer={transfer}
            onCancelled={loaded.replace} onStale={loaded.refresh} />}
          <p><Link className={buttonClassName({ variant: 'outline' })} to={HOME_PATH}>Tiếp tục mua sắm</Link></p>
        </>}
    </div>
  </div>
}
