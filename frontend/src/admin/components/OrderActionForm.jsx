import { formatMoney } from '../../lib/format.js'
import { orderStatusLabel } from '../lib/orders.js'
import { PRODUCT_CONTROL } from './ProductUi.jsx'

export default function OrderActionForm({ workflow }) {
  const { order, intent, next, blocked, codDelivery, collected, busy, reason, note, setReason, setNote, setCollected, submitStatus } = workflow
  return <form id="order-status-form" className="flex flex-col gap-3 rounded-xl border border-admin-border p-4" onSubmit={submitStatus}>
        <p className="m-0 text-sm font-semibold">{intent === 'cancel' ? 'Bạn xác nhận hủy đơn ' + order.OrderCode + '?' : next ? orderStatusLabel(order.OrderStatus) + ' → ' + orderStatusLabel(next[0]) : 'Đơn hàng không còn bước xử lý tiếp theo.'}</p>
        {intent === 'cancel' ? <>
          {order.OrderStatus === 'Shipping' && <p className="m-0 text-xs text-amber-700">Hàng đang vận chuyển: hủy đơn sẽ tạo hồ sơ hàng giao thất bại chờ về kho; tồn kho chưa được hoàn ngay.</p>}
          {order.PaymentStatus === 'Paid' && <p className="m-0 text-xs text-amber-700">Đơn đã thanh toán. Sau khi hủy cần xử lý hoàn tiền ở nghiệp vụ thanh toán.</p>}
          <label className="flex flex-col gap-1.5 text-xs font-semibold">Lý do hủy<textarea required className={PRODUCT_CONTROL + ' min-h-20 font-normal'} value={reason} disabled={busy} maxLength={2000} onChange={(event) => setReason(event.target.value)} /></label>
        </> : <>
          {blocked && <p className="m-0 text-xs text-amber-700">{blocked}</p>}
          {codDelivery && <label className="flex items-start gap-2 text-xs"><input type="checkbox" className="mt-0.5 accent-admin-blue" checked={collected} disabled={busy} onChange={(event) => setCollected(event.target.checked)} /><span>Tôi xác nhận đã giao hàng thành công và đã thu đủ {formatMoney(order.TotalAmount)} tiền COD.</span></label>}
        </>}
        <label className="flex flex-col gap-1.5 text-xs font-semibold">Ghi chú xử lý<textarea className={PRODUCT_CONTROL + ' min-h-16 font-normal'} value={note} disabled={busy} maxLength={2000} onChange={(event) => setNote(event.target.value)} /></label>
      </form>
}
