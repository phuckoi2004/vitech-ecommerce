import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useCustomerSession from '../../../hooks/useCustomerSession.js'
import { cancelOrder } from '../../../lib/order-api.js'
import { cancelReturn } from '../../../lib/return-api.js'
import { returnRequestPath } from '../../routes/paths.js'

// Cancels a Pending order (POST /orders/{id}/cancel) after the customer confirms. `onCancelled(order)` receives the
// cancelled order; after a failure `onStale()` reads the order again, since it may have changed or been cancelled.
// `transfer` adds a warning for a transfer order that may already have been paid.

// Refusals of OrderService.cancel_customer_order: only a Pending order that is not paid can be cancelled by its customer.
const REFUSED = {
  order_not_cancellable: 'Đơn hàng không thể huỷ ở trạng thái hiện tại.',
  order_paid_not_cancellable: 'Đơn hàng đã được thanh toán nên không thể tự huỷ. Vui lòng liên hệ VieTech để được hỗ trợ.',
  return_not_cancellable: 'Phiếu đã chốt đơn đổi hoặc đã đóng nên không thể hủy.',
}

export default function CancelOrder({ order, transfer, onCancelled, onStale }) {
  const { withAccessToken } = useCustomerSession()
  const navigate = useNavigate()
  const exchange = Boolean(order.SourceReturnRequestId)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function cancel() {
    setBusy(true)
    setError('')
    try {
      if (exchange) {
        await withAccessToken((token) => cancelReturn(token, order.SourceReturnRequestId))
        navigate(returnRequestPath(order.SourceReturnRequestId))
      } else {
        onCancelled(await withAccessToken((token) => cancelOrder(token, order.OrderId)))
      }
    } catch (failure) {
      setError(failure?.code && Object.hasOwn(REFUSED, failure.code) ? REFUSED[failure.code]
        : `Chưa huỷ được ${exchange ? 'phiếu đổi trả' : 'đơn hàng'}. ${failure?.message ?? ''}`.trim())
      onStale()
    } finally {
      setBusy(false)
    }
  }

  if (!confirming) {
    return <div className="order-cancel">
      <button type="button" className="od-button is-muted" onClick={() => setConfirming(true)}>{exchange ? 'Hủy phiếu' : 'Hủy đơn'}</button>
      {error && <p className="order-error" role="alert">{error}</p>}
    </div>
  }
  return <div className="order-cancel is-confirming" role="group" aria-label={exchange ? 'Xác nhận hủy phiếu đổi trả' : 'Xác nhận huỷ đơn hàng'}>
    <p>{exchange ? `Hủy phiếu đổi trả và đơn đổi ${order.OrderCode}? Hàng đang giữ sẽ được giải phóng.` : `Huỷ đơn hàng ${order.OrderCode}? Thao tác này không thể hoàn tác.`}</p>
    {transfer && <p>Nếu bạn đã chuyển khoản, đừng huỷ đơn: trang sẽ tự cập nhật khi VieTech nhận được thanh toán.</p>}
    <div className="order-actions">
      <button type="button" className="order-danger-button" disabled={busy} onClick={cancel}>{busy ? 'Đang huỷ…' : 'Xác nhận huỷ'}</button>
      <button type="button" className="order-link-button" disabled={busy} onClick={() => setConfirming(false)}>Không huỷ</button>
    </div>
    {error && <p className="order-error" role="alert">{error}</p>}
  </div>
}
