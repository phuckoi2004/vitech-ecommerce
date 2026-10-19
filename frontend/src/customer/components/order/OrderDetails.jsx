import Money from '../../../components/shared/Money.jsx'
import { formatDateTime } from '../../../lib/format.js'

// What the order holds (OrderDetailResponse): its lines at the prices the server charged, the amounts that make up
// TotalAmount, and where it is delivered. Read-only; every value is the server's.
export default function OrderDetails({ order }) {
  const items = order.Items ?? []
  return <section id="order-details" className="order-details" aria-labelledby="order-details-title">
    <h2 id="order-details-title" className="order-section-title">Thông tin đơn hàng</h2>
    {items.length > 0 && <ul className="order-items" aria-label="Sản phẩm trong đơn hàng">
      {items.map((item) => <li key={item.OrderItemId}>
        <div className="order-item-name">
          <strong>{item.ProductName}</strong>
          {item.VariantInfo && <span>{item.VariantInfo}</span>}
        </div>
        <span className="order-item-quantity">x{item.Quantity}</span>
        <Money className="order-item-total" value={item.LineTotal} />
      </li>)}
    </ul>}
    <div className="order-details-grid">
      <dl className="order-totals">
        <div><dt>Tạm tính</dt><dd><Money value={order.Subtotal} /></dd></div>
        <div><dt>Phí vận chuyển</dt><dd><Money value={order.ShippingFee} /></dd></div>
        {Number(order.DiscountAmount) > 0 && <div><dt>Giảm giá</dt><dd>−<Money value={order.DiscountAmount} /></dd></div>}
        <div className="is-total"><dt>Tổng cộng</dt><dd><Money value={order.TotalAmount} /></dd></div>
      </dl>
      <dl className="order-receiver">
        <div><dt>Người nhận</dt><dd>{order.ReceiverName} · {order.ReceiverPhone}</dd></div>
        <div><dt>Địa chỉ giao hàng</dt><dd>{order.ShippingAddress}</dd></div>
        <div><dt>Ngày đặt</dt><dd>{formatDateTime(order.OrderedAt)}</dd></div>
        {order.CustomerNote && <div><dt>Ghi chú</dt><dd>{order.CustomerNote}</dd></div>}
      </dl>
    </div>
  </section>
}
