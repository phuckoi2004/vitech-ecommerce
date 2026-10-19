import { Link } from 'react-router-dom'
import Money from '../../../components/shared/Money.jsx'
import { formatDateTime } from '../../../lib/format.js'
import { orderPath } from '../../routes/paths.js'

// Why the last attempt to place the order failed (`failure` from orderFailure, without the field errors the form shows
// itself). When the outcome is unknown the order may exist, so nothing is sent again: the customer checks their latest
// order first. `lookup`: null (not checked yet), {status: 'checking'}, {status: 'error', message} or
// {status: 'done', order} with the newest OrderSummary or null. `signInTo` is the sign-in page that comes back here.
export default function OrderProblem({ failure, lookup, signInTo, onCheck }) {
  const unknown = failure.outcome === 'unknown'
  return <div className={`checkout-order-problem${unknown ? ' is-unknown' : ''}`}>
    <p role="alert">{failure.message}</p>
    {failure.action === 'signIn' && <p><Link to={signInTo}>Đăng nhập lại</Link></p>}
    {unknown && <OrderLookup lookup={lookup} onCheck={onCheck} />}
  </div>
}

function OrderLookup({ lookup, onCheck }) {
  if (lookup?.status === 'checking') return <p role="status">Đang kiểm tra đơn hàng…</p>
  if (lookup?.status === 'done') {
    const order = lookup.order
    return <div role="status">
      {order ? <>
        <p>
          Đơn hàng gần nhất của bạn: <strong>{order.OrderCode}</strong>, đặt lúc {formatDateTime(order.OrderedAt)},
          tổng <Money value={order.TotalAmount} />. <Link to={orderPath(order.OrderId)}>Xem đơn hàng</Link>
        </p>
        <p>Nếu đó không phải đơn bạn vừa đặt, bạn có thể đặt hàng lại.</p>
      </> : <p>Bạn chưa có đơn hàng nào, nên đơn vừa rồi chưa được tạo. Bạn có thể đặt hàng lại.</p>}
    </div>
  }
  return <div>
    {lookup?.status === 'error' && <p>Chưa kiểm tra được đơn hàng. {lookup.message}</p>}
    <button type="button" onClick={onCheck}>{lookup?.status === 'error' ? 'Kiểm tra lại' : 'Kiểm tra đơn hàng'}</button>
  </div>
}
