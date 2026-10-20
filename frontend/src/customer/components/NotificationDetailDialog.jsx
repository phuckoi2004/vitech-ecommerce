import { Link } from 'react-router-dom'
import { buttonClassName } from '../../components/shared/buttonStyles.js'
import ErrorState from '../../components/shared/ErrorState.jsx'
import LoadingState from '../../components/shared/LoadingState.jsx'
import Money from '../../components/shared/Money.jsx'
import useApiData from '../../hooks/useApiData.js'
import useCustomerRequest from '../../hooks/useCustomerRequest.js'
import { formatDateTime } from '../../lib/format.js'
import { notificationStatus } from '../notifications.js'
import { orderPath } from '../routes/paths.js'
import ProductModal from './product/ProductModal.jsx'

function ResourceDetail({ target }) {
  const send = useCustomerRequest()
  const detail = useApiData(target.path, signal => send(target.path, { signal }))
  if (detail.loading) return <LoadingState />
  if (detail.error) return <ErrorState message={detail.error} onRetry={detail.reload} />
  const data = detail.data
  const order = target.type === 'Order'
  const fields = order ? [
    ['Mã đơn hàng', data.OrderCode], ['Trạng thái đơn', notificationStatus(data.OrderStatus)],
    ['Thanh toán', data.PaymentStatus === 'Pending' ? 'Chưa thanh toán' : notificationStatus(data.PaymentStatus)],
    ['Ngày đặt', formatDateTime(data.OrderedAt)], ['Người nhận', data.ReceiverName], ['Địa chỉ giao hàng', data.ShippingAddress],
  ] : [
    ['Mã yêu cầu', data.RequestCode], ['Trạng thái', notificationStatus(data.Status)], ['Ngày gửi', formatDateTime(data.RequestedAt)],
    [target.type === 'WarrantyRequest' ? 'Mô tả sự cố' : 'Lý do đổi trả', data.IssueDescription || data.Reason],
    ['Lý do xét điều kiện', data.EligibilityReason],
    ['Kết quả bảo hành', data.ResultApprovedAt && data.ResultType ? notificationStatus(data.ResultType) : null],
    ['Nội dung kết quả', data.ResultApprovedAt ? data.ResultNote : null],
  ]
  const history = data.StatusHistories || data.Histories || []
  return <div className="notification-detail">
    <dl>{fields.filter(([, value]) => value !== null && value !== undefined && value !== '' && value !== false).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    {order && <>
      <ul className="notification-order-items">{(data.Items ?? []).map(item => <li key={item.OrderItemId}>
        <div><strong>{item.ProductName}</strong><p>{item.VariantInfo} · Số lượng: {item.Quantity}</p></div><Money value={item.LineTotal} />
      </li>)}</ul>
      <p className="notification-total">Tổng đơn hàng <Money value={data.TotalAmount} /></p>
      {data.CancelReason && <p className="shopping-text">Lý do hủy: {data.CancelReason}</p>}
      {/* The order page shows the payment status and, while a transfer is awaited, its QR. */}
      <p><Link className={buttonClassName({ variant: 'outline', size: 'sm' })} to={orderPath(data.OrderId)}>Mở trang đơn hàng</Link></p>
    </>}
    {history.length > 0 && <section><h3>Lịch sử cập nhật</h3><ol className="notification-history">
      {[...history].sort((a, b) => Date.parse(a.ChangedAt) - Date.parse(b.ChangedAt)).map((item, index) => <li key={item.OrderStatusHistoryId || item.ServiceRequestHistoryId || index}>
        <strong>{notificationStatus(item.NewStatus)}</strong><time dateTime={item.ChangedAt}>{formatDateTime(item.ChangedAt)}</time>
        {item.Note && <p className="shopping-text">{item.Note}</p>}
      </li>)}
    </ol></section>}
  </div>
}

export default function NotificationDetailDialog({ target, onClose }) {
  return <ProductModal open title={target.title} onClose={onClose} className="notification-dialog"><ResourceDetail key={target.path} target={target} /></ProductModal>
}
