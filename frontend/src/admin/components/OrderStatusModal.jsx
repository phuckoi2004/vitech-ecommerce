import { canCancelOrder } from '../lib/orders.js'
import { ErrorState } from '../../components/shared/index.js'
import Modal from './Modal.jsx'
import OrderActionForm from './OrderActionForm.jsx'
import { ProductButton } from './ProductUi.jsx'

export default function OrderStatusModal({ workflow }) {
  const { order, intent, busy, canUpdate, next, blocked, codDelivery, collected, reason, choose, error, payment, serials } = workflow
  if (!order || !intent || !canUpdate) return null
  const cancelling = intent === 'cancel'
  return <Modal open variant="tailwind" title={cancelling ? 'Hủy đơn hàng' : 'Cập nhật trạng thái đơn hàng'} description={'Đơn ' + order.OrderCode} busy={busy} onClose={() => choose(null)} footer={<>
    <ProductButton secondary disabled={busy} onClick={() => choose(null)}>Đóng</ProductButton>
    <ProductButton type="submit" form="order-status-form" disabled={busy || (cancelling ? !canCancelOrder(order) || !reason.trim() : !next || Boolean(blocked) || (codDelivery && !collected))}>{busy ? 'Đang cập nhật…' : cancelling ? 'Xác nhận hủy đơn' : codDelivery ? 'Xác nhận giao và thu tiền' : next?.[1] ?? 'Không còn bước tiếp theo'}</ProductButton>
  </>}>
    {error && <p role="alert" className="mb-3 rounded-[10px] bg-red-50 p-3 text-xs text-red-700">{error}</p>}
    {!cancelling && ['Processing', 'Shipping'].includes(order.OrderStatus) && payment.error && <ErrorState message={payment.error} onRetry={payment.refresh} className="py-3" />}
    {!cancelling && order.OrderStatus === 'Processing' && serials.error && <ErrorState message={serials.error} onRetry={serials.refresh} className="py-3" />}
    <OrderActionForm workflow={workflow} />
  </Modal>
}
