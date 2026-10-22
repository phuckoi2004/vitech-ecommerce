import { Link } from 'react-router-dom'
import Money from '../../../components/shared/Money.jsx'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { formatDate, formatDateTime } from '../../../lib/format.js'
import { REVIEWABLE_ORDER_STATUSES } from '../../../lib/review-api.js'
import { formatStatus } from '../../../lib/status-labels.js'
import { productPath, productReviewsPath } from '../../routes/paths.js'
import { lineDisplay } from '../cart/cartLines.js'
import useProductDetails from '../cart/useProductDetails.js'
import StoreImage from '../StoreImage.jsx'
import { historyEntries, ORDER_STEPS, orderStep, paymentTone, statusTone } from './orderDetail.js'
import { ORDER_STATUS, paymentStatusText } from './orderPayment.js'

// The cards of the customer order page (Figma "Chi tiết đơn hàng", frame 865:371). Every value is the server's
// (OrderDetailResponse); product images and links come from the public product details, when the product still has one.

// Code, date, method and status, the 4 progress steps (none for a cancelled order), then `children`: what the status
// means for the customer.
export function OrderProgress({ order, methodLabel, children }) {
  const step = orderStep(order.OrderStatus)
  return <section className="od-card od-status-card" aria-labelledby="od-order-title">
    <div className="od-order-head">
      <div>
        <h2 id="od-order-title" className="od-order-title">Đơn hàng #<span>{order.OrderCode}</span></h2>
        {order.SourceReturnRequestId && <p className="font-semibold text-red-600">Đơn đổi trả{Number(order.TotalAmount) === 0 ? ' · 0đ · Không cần thanh toán' : ' · Thanh toán phần chênh lệch'}</p>}
        <p className="od-muted">Ngày đặt: {formatDate(order.OrderedAt)} • Phương thức: {methodLabel}</p>
      </div>
      <dl className="od-order-status">
        <dt className="sr-only">Trạng thái đơn hàng</dt>
        <dd className={`od-badge is-${statusTone(order.OrderStatus)}`}>{formatStatus(order.OrderStatus, ORDER_STATUS)}</dd>
      </dl>
    </div>
    {step > 0 && <div className="od-progress">
      <div className="od-progress-head">
        <h3>Tiến trình xử lý đơn hàng</h3>
        <span>Bước {step}/{ORDER_STEPS.length}</span>
      </div>
      <ol className="od-steps" aria-label="Các bước xử lý đơn hàng">
        {ORDER_STEPS.map((item, index) => <li key={item.label} className={index < step ? 'is-done' : ''}
          aria-current={index + 1 === step ? 'step' : undefined}>
          <span className="od-step-dot" aria-hidden="true">{index + 1}</span>{item.label}
        </li>)}
      </ol>
    </div>}
    {children}
  </section>
}

export function OrderItems({ order }) {
  const items = order.Items ?? []
  const details = useProductDetails(items.map((item) => item.ProductId).filter(Boolean))
  const lines = items.map((item) => ({ item, ...lineDisplay(item, item.ProductId ? details[item.ProductId] : null) }))
  const quantity = items.reduce((sum, item) => sum + item.Quantity, 0)
  const slugs = [...new Set(lines.map((line) => line.slug).filter(Boolean))]
  // Reviews are written on the product page, once per line, for a received order (ReviewService).
  const reviewable = REVIEWABLE_ORDER_STATUSES.includes(order.OrderStatus)

  return <section className="od-card od-items-card" aria-labelledby="od-items-title">
    <h2 id="od-items-title" className="od-card-title">Sản phẩm đã đặt</h2>
    {items.length ? <ul className="od-items" aria-label="Sản phẩm trong đơn hàng">
      {lines.map(({ item, imageUrl, slug }) => {
        const image = <StoreImage src={imageUrl} alt="" loading="lazy" decoding="async"
          fallback={<span className="od-item-noimage">VieTech</span>} />
        return <li key={item.OrderItemId}>
          {slug ? <Link className="od-item-media" to={productPath(slug)} tabIndex={-1} aria-hidden="true">{image}</Link>
            : <span className="od-item-media" aria-hidden="true">{image}</span>}
          <div className="od-item-info">
            <strong>{slug ? <Link to={productPath(slug)}>{item.ProductName}</Link> : item.ProductName}</strong>
            {item.VariantInfo && <span>Phiên bản: {item.VariantInfo}</span>}
            <span>Số lượng: {item.Quantity}</span>
            <span>Serial / IMEI: {(item.SerialNumbers ?? []).join(', ')}</span>
          </div>
          <div className="od-item-price">
            <Money value={item.LineTotal} />
            <span>x {item.Quantity} sản phẩm</span>
            {item.ReviewId ? <span className="od-item-reviewed">✓ Đã đánh giá</span>
              : reviewable && slug && <Link to={productReviewsPath(slug, order.OrderId)}>Đánh giá sản phẩm</Link>}
          </div>
        </li>
      })}
    </ul> : <p className="od-muted">Đơn hàng không có sản phẩm.</p>}
    <div className="od-items-foot">
      <span>{quantity} sản phẩm trong đơn hàng</span>
      {slugs.length === 1 && <Link to={productPath(slugs[0])}>Xem chi tiết sản phẩm ›</Link>}
    </div>
  </section>
}

// The amounts that make up TotalAmount (Subtotal − DiscountAmount + ShippingFee).
export function OrderTotals({ order }) {
  const discount = Number(order.DiscountAmount) > 0
  return <section className="od-card od-totals-card" aria-labelledby="od-totals-title">
    <h2 id="od-totals-title" className="od-card-title">Chi tiết thanh toán</h2>
    <dl className="od-totals">
      <div><dt>Tạm tính</dt><dd><Money value={order.Subtotal} /></dd></div>
      <div><dt>Phí vận chuyển</dt><dd><Money value={order.ShippingFee} /></dd></div>
      <div><dt>Giảm giá</dt><dd>{discount && '−'}<Money value={order.DiscountAmount} /></dd></div>
      {Number(order.ExchangeCreditAmount) > 0 && <div><dt>Trong đó giá trị dùng đổi</dt><dd><Money value={order.ExchangeCreditAmount} /></dd></div>}
      <div className="is-total"><dt>Tổng thanh toán</dt><dd><Money value={order.TotalAmount} /></dd></div>
    </dl>
  </section>
}

// The account email (orders keep no receiver email) beside the receiver phone, as in Figma.
export function OrderRecipient({ order }) {
  const { user } = useCustomerSession()
  return <section className="od-card od-side-card od-recipient-card" aria-labelledby="od-recipient-title">
    <h2 id="od-recipient-title" className="od-card-title">Thông tin nhận hàng</h2>
    <dl className="od-facts">
      <div><dt>Người nhận</dt><dd><strong>{order.ReceiverName}</strong><span>{[order.ReceiverPhone, user?.Email].filter(Boolean).join(' • ')}</span></dd></div>
      <div><dt>Địa chỉ giao hàng</dt><dd>{order.ShippingAddress}</dd></div>
      {order.CustomerNote && <div><dt>Ghi chú</dt><dd>{order.CustomerNote}</dd></div>}
    </dl>
  </section>
}

// No carrier or tracking number is stored: the method and the hand-over and delivery times.
export function OrderShipping({ order, methodName }) {
  return <section className="od-card od-side-card" aria-labelledby="od-shipping-title">
    <h2 id="od-shipping-title" className="od-card-title">Thông tin vận chuyển</h2>
    <dl className="od-lines">
      <div><dt>Hình thức</dt><dd>{methodName}</dd></div>
      {order.ShippedAt && <div><dt>Bàn giao vận chuyển</dt><dd>{formatDateTime(order.ShippedAt)}</dd></div>}
      {order.DeliveredAt && <div><dt>Giao thành công</dt><dd>{formatDateTime(order.DeliveredAt)}</dd></div>}
    </dl>
    {!order.ShippedAt && order.OrderStatus !== 'Cancelled' && <p className="od-muted">
      Thông tin vận chuyển sẽ được cập nhật khi đơn hàng được bàn giao cho đơn vị vận chuyển.
    </p>}
  </section>
}

// The method, its payment status and `children`: what to do next (pay on delivery, the QR above, a retry).
export function OrderPayment({ order, methodName, cod, children }) {
  return <section className="od-card od-side-card" aria-labelledby="od-payment-title">
    <h2 id="od-payment-title" className="od-card-title">Phương thức thanh toán</h2>
    <dl className="od-payment">
      <div><dt className="sr-only">Hình thức thanh toán</dt><dd className="od-payment-name">{methodName}</dd></div>
      <div>
        <dt className="sr-only">Trạng thái thanh toán</dt>
        <dd><span className={`od-badge is-${paymentTone(order)}`}>{paymentStatusText(order, cod)}</span></dd>
      </div>
    </dl>
    {children}
  </section>
}

// StatusHistories, newest first: the latest in the colour of its status, earlier ones as done.
export function OrderStatusLog({ order }) {
  const entries = historyEntries(order.StatusHistories)
  return <section className="od-card od-log-card" aria-labelledby="od-log-title">
    <h2 id="od-log-title" className="od-card-title">Lịch sử cập nhật đơn hàng</h2>
    {entries.length ? <ol className="od-log">
      {entries.map((entry, index) => <li key={entry.id} className={`is-${index === 0 ? statusTone(entry.status) : 'done'}`}>
        <span className="od-log-marker" aria-hidden="true" />
        <div className="od-log-event">
          <strong>{formatStatus(entry.status, ORDER_STATUS)}</strong>
          {entry.text && <p>{entry.text}</p>}
        </div>
        <time dateTime={entry.at} title={formatDateTime(entry.at)}>{formatDate(entry.at)}</time>
      </li>)}
    </ol> : <p className="od-muted">Chưa có cập nhật nào cho đơn hàng này.</p>}
  </section>
}
