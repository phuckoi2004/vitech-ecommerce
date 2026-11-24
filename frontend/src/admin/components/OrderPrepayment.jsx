import { formatDateTime, formatMoney } from '../../lib/format.js'
import { hasPrepayment, remainingAmount } from '../../lib/prepayment.js'
import { formatStatus } from '../../lib/status-labels.js'
import useAdminQuery from '../hooks/useAdminQuery.js'

export default function OrderPrepayment({ order }) {
  const enabled = hasPrepayment(order)
  const transactions = useAdminQuery('/admin/orders/' + encodeURIComponent(order.OrderId) + '/payments', {}, enabled)
  if (!enabled) return null
  return <section aria-label="Thanh toán trả trước" className="flex min-w-0 flex-col gap-3 rounded-[14px] border border-admin-border bg-white p-4">
    <h3 className="m-0 text-[15px] font-semibold">Thanh toán trả trước</h3>
    <p className="m-0 text-xs">Trả trước 20% qua QR, phần còn lại thu khi nhận hàng.</p>
    <dl className="m-0 grid grid-cols-2 gap-2 text-xs">
      <dt>Khoản trả trước (20%)</dt><dd className="m-0 text-right">{formatMoney(order.PrepaymentAmount)}</dd>
      <dt>Đã thực nhận</dt><dd className="m-0 text-right">{formatMoney(order.ReceivedAmount ?? 0)}</dd>
      <dt>Còn phải thu</dt><dd className="m-0 text-right font-semibold">{formatMoney(remainingAmount(order))}</dd>
    </dl>
    <h4 className="m-0 text-xs font-semibold">Lịch sử thanh toán</h4>
    {transactions.loading ? <p className="m-0 text-xs text-admin-muted">Đang tải giao dịch…</p>
      : transactions.error ? <p className="m-0 text-xs text-admin-red">{transactions.error} <button type="button" onClick={transactions.refresh} className="underline">Thử lại</button></p>
        : transactions.data?.length ? <ul className="m-0 flex list-none flex-col gap-2 p-0 text-xs">
          {transactions.data.map((tx) => <li key={tx.PaymentTransactionId} className="flex flex-col gap-1 border-t border-admin-border pt-2">
            <span>{tx.TransactionType === 'Refund' ? 'Hoàn tiền' : tx.QrData || tx.GatewayTransactionCode ? 'Chuyển khoản qua QR' : 'Thu khi nhận hàng'} · {formatStatus(tx.Status)}</span>
            <span>{formatMoney(tx.Amount)} · {formatDateTime(tx.PaidAt ?? tx.CreatedAt)}</span>
          </li>)}
        </ul> : <p className="m-0 text-xs text-admin-muted">Chưa có giao dịch.</p>}
  </section>
}
