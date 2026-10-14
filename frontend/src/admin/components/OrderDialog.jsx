import { ErrorState, LoadingState } from '../../components/shared/index.js'
import { formatDateTime, formatMoney } from '../../lib/format.js'
import useOrderWorkflow from '../hooks/useOrderWorkflow.js'
import { canCancelOrder, orderStatusLabel, PAYMENT_LABELS } from '../lib/orders.js'
import { releaseOrderSerial, updateOrderNote } from '../services/orders.js'
import AdminTable from './AdminTable.jsx'
import Modal from './Modal.jsx'
import OrderActionForm from './OrderActionForm.jsx'
import OrderBadge from './OrderBadge.jsx'
import { InternalNote, SerialRow } from './OrderControls.jsx'
import { ProductButton } from './ProductUi.jsx'

function DetailField({ label, children }) {
  return <div className="min-w-0"><dt className="mb-1 text-xs text-admin-muted">{label}</dt><dd className="m-0 text-sm break-words whitespace-pre-wrap">{children || '—'}</dd></div>
}

export default function OrderDialog({ orderId, initialAction, onClose, onDone }) {
  const workflow = useOrderWorkflow(orderId, initialAction, onDone)
  const { detail, order, payment, needsSerials, serials, intent, busy, error, notice, canUpdate, next, codDelivery, serialItems, blocked, write, assign, choose, reason, collected, setNotice, setCollected } = workflow
  const confirming = canUpdate && Boolean(intent)
  const title = confirming ? intent === 'cancel' ? 'Hủy đơn hàng' : 'Cập nhật trạng thái đơn hàng' : 'Chi tiết đơn hàng'
  const itemColumns = [
    { key: 'ProductName', label: 'Sản phẩm / Biến thể', render: (name, item) => <span className="block max-w-[240px] break-words">{name}<span className="mt-1 block text-[11px] text-admin-muted">{item.VariantInfo}</span></span> },
    { key: 'Sku', label: 'SKU', render: (value) => <span className="break-all">{value}</span> },
    { key: 'Quantity', label: 'SL' },
    { key: 'UnitPrice', label: 'Đơn giá', render: formatMoney },
    { key: 'DiscountAmount', label: 'Giảm giá', render: formatMoney },
    { key: 'LineTotal', label: 'Thành tiền', render: formatMoney },
  ]
  return <Modal open variant="tailwind" wide title={title} description={order ? 'Đơn ' + order.OrderCode : undefined} onClose={onClose} busy={busy} footer={<>
    <ProductButton secondary disabled={busy} onClick={onClose}>Đóng</ProductButton>
    {order && canUpdate && !confirming && <>
      {canCancelOrder(order) && <ProductButton secondary disabled={busy} onClick={() => choose('cancel')}>Hủy đơn hàng</ProductButton>}
      {next && <ProductButton disabled={busy} onClick={() => choose('advance')}>{next[1]}</ProductButton>}
    </>}
    {confirming && order && <>
      <ProductButton secondary disabled={busy} onClick={() => choose(null)}>Quay lại chi tiết</ProductButton>
      <ProductButton type="submit" form="order-status-form" disabled={busy || (intent === 'advance' ? !next || Boolean(blocked) || (codDelivery && !collected) : !canCancelOrder(order) || !reason.trim())}>{busy ? 'Đang cập nhật…' : intent === 'cancel' ? 'Xác nhận hủy đơn' : codDelivery ? 'Xác nhận giao và thu tiền' : next?.[1] ?? 'Không còn bước tiếp theo'}</ProductButton>
    </>}
  </>}>
    {detail.loading ? <LoadingState label="Đang tải đơn hàng…" /> : detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} /> : order && <div className="flex flex-col gap-5">
      {error && <p role="alert" className="m-0 rounded-[10px] bg-red-50 p-3 text-xs text-red-700">{error}</p>}
      {notice && <p role="status" className="m-0 rounded-[10px] bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
      <dl className="m-0 grid grid-cols-2 gap-4 rounded-xl bg-admin-page p-4">
        <DetailField label="Trạng thái"><OrderBadge value={order.OrderStatus} /></DetailField>
        <DetailField label="Ngày đặt">{formatDateTime(order.OrderedAt)}</DetailField>
        <DetailField label="Người nhận">{order.ReceiverName}</DetailField><DetailField label="Số điện thoại">{order.ReceiverPhone}</DetailField>
        <div className="col-span-2"><DetailField label="Địa chỉ giao hàng">{order.ShippingAddress}</DetailField></div>
        <DetailField label="Thanh toán">{PAYMENT_LABELS[order.PaymentStatus] ?? order.PaymentStatus}</DetailField>
        <DetailField label="Phương thức thanh toán">{payment.loading ? 'Đang tải…' : payment.data?.Name ?? 'Chưa tải được'}</DetailField>
        {order.CustomerNote && <div className="col-span-2"><DetailField label="Ghi chú khách hàng">{order.CustomerNote}</DetailField></div>}
        {order.CancelReason && <div className="col-span-2"><DetailField label="Lý do hủy">{order.CancelReason}</DetailField></div>}
      </dl>
      {payment.error && <ErrorState title="Chưa tải được phương thức thanh toán" message={payment.error} onRetry={payment.refresh} className="py-2" />}
      {confirming && <OrderActionForm workflow={workflow} />}
      <section aria-label="Sản phẩm trong đơn"><h3 className="mb-3 text-sm font-semibold">Sản phẩm trong đơn</h3><AdminTable columns={itemColumns} rows={order.Items ?? []} rowKey="OrderItemId" label="Sản phẩm trong đơn" emptyText="Đơn hàng chưa có sản phẩm." className="min-w-[650px] [&_td]:py-3" /></section>
      <dl className="m-0 ml-auto grid w-[320px] max-w-full grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <dt className="text-admin-muted">Tiền hàng</dt><dd className="m-0 text-right">{formatMoney(order.Subtotal)}</dd>
        <dt className="text-admin-muted">Phí vận chuyển</dt><dd className="m-0 text-right">{formatMoney(order.ShippingFee)}</dd>
        <dt className="text-admin-muted">Giảm giá đơn hàng</dt><dd className="m-0 text-right">{formatMoney(order.DiscountAmount)}</dd>
        <dt className="border-t border-admin-border pt-2 font-semibold">Tổng thanh toán</dt><dd className="m-0 border-t border-admin-border pt-2 text-right font-semibold text-admin-blue">{formatMoney(order.TotalAmount)}</dd>
      </dl>
      {needsSerials && <section aria-label="Serial/IMEI của đơn" className="flex flex-col gap-3"><h3 className="m-0 text-sm font-semibold">Serial/IMEI của đơn</h3>
        {serials.loading ? <LoadingState label="Đang tải Serial/IMEI…" /> : serials.error ? <ErrorState message={serials.error} onRetry={serials.refresh} /> : <>
          {serialItems.filter((item) => item.IsSerialTracked).map((item) => <SerialRow key={item.OrderItemId} item={item} busy={busy} editable={canUpdate && order.OrderStatus === 'Processing'} onAssign={assign} onRelease={(number) => write((token) => releaseOrderSerial(token, orderId, number), () => { serials.refresh(); setNotice('Đã gỡ Serial/IMEI.'); setCollected(false) })} />)}
          {!serialItems.some((item) => item.IsSerialTracked) && <p className="m-0 text-xs text-admin-muted">Các sản phẩm trong đơn không yêu cầu quản lý Serial/IMEI.</p>}
        </>}
      </section>}
      {!confirming && (canUpdate ? <InternalNote key={order.InternalNote ?? ''} order={order} busy={busy} onSave={(value) => write((token) => updateOrderNote(token, orderId, { InternalNote: value }), () => { detail.refresh(); setNotice('Đã lưu ghi chú nội bộ.') })} /> : <dl className="m-0"><DetailField label="Ghi chú nội bộ">{order.InternalNote}</DetailField></dl>)}
      <section aria-label="Lịch sử trạng thái"><h3 className="mb-3 text-sm font-semibold">Lịch sử trạng thái</h3>
        {order.StatusHistories?.length ? <ol className="m-0 flex list-none flex-col gap-3 p-0">{order.StatusHistories.map((entry) => <li key={entry.OrderStatusHistoryId} className="border-l-2 border-admin-border pl-3 text-xs">
          <div className="flex items-center justify-between gap-3"><strong>{entry.OldStatus ? orderStatusLabel(entry.OldStatus) + ' → ' : 'Tạo đơn → '}{orderStatusLabel(entry.NewStatus)}</strong><time dateTime={entry.ChangedAt} className="text-admin-muted">{formatDateTime(entry.ChangedAt)}</time></div>
          {entry.Note && <p className="mt-1 mb-0 break-words whitespace-pre-wrap text-admin-muted">{entry.Note}</p>}
        </li>)}</ol> : <p className="m-0 text-xs text-admin-muted">Chưa có lịch sử trạng thái.</p>}
      </section>
    </div>}
  </Modal>
}
