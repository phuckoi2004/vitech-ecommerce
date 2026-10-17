import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import { formatDate, formatDateTime, formatMoney } from '../../lib/format.js'
import historyDot from '../assets/order-history-dot.svg'
import AdminTable from '../components/AdminTable.jsx'
import OrderBadge from '../components/OrderBadge.jsx'
import { InternalNote, SerialRow } from '../components/OrderControls.jsx'
import OrderProgress from '../components/OrderProgress.jsx'
import OrderStatusModal from '../components/OrderStatusModal.jsx'
import { ProductButton } from '../components/ProductUi.jsx'
import useOrderWorkflow from '../hooks/useOrderWorkflow.js'
import { canCancelOrder, orderListSearch, orderStatusLabel, PAYMENT_LABELS } from '../lib/orders.js'
import { releaseOrderSerial, updateOrderNote } from '../services/orders.js'

const CARD = 'min-w-0 rounded-[14px] border border-admin-border bg-white px-[18px] py-4'
const TITLE = 'm-0 text-[15px] leading-[normal] font-semibold'

function Info({ label, children, strong = false }) {
  return <div className="min-w-0"><dt className="mb-2 text-[11px] leading-[normal] font-medium text-admin-muted">{label}</dt><dd className={'m-0 text-xs leading-[normal] break-words whitespace-pre-wrap ' + (strong ? 'font-semibold' : 'font-medium')}>{children || '—'}</dd></div>
}

export default function OrderDetailPage() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [extraOpen, setExtraOpen] = useState(false)
  const { onSubPage } = useOutletContext() ?? {}
  const workflow = useOrderWorkflow(orderId, null, statusDone)
  const { detail, order, payment, needsSerials, serials, serialItems, canUpdate, next, busy, error, notice, intent, write, assign, choose, setNotice, setCollected } = workflow
  useEffect(() => {
    onSubPage?.(order?.OrderCode ?? null)
    return () => onSubPage?.(null)
  }, [onSubPage, order?.OrderCode])

  function statusDone(message) { choose(null); setNotice(message); detail.refresh(); serials.refresh() }
  function back() { navigate('/admin/orders' + orderListSearch(params)) }
  const columns = [
    { key: 'ProductName', label: 'Sản phẩm', className: 'w-[49.7%]', render: (name, item) => <div className="min-w-0 break-words"><span className="font-medium">{name}</span><span className="mt-1 block text-[10px] text-admin-muted">{item.VariantInfo}</span><span className="mt-0.5 block text-[10px] break-all text-admin-muted">SKU: {item.Sku}</span>{Number(item.DiscountAmount) > 0 && <span className="mt-0.5 block text-[10px] text-admin-muted">Giảm: {formatMoney(item.DiscountAmount)}</span>}</div> },
    { key: 'Quantity', label: 'SL', className: 'w-[13.2%]' },
    { key: 'UnitPrice', label: 'Đơn giá', className: 'w-[17.5%]', render: formatMoney },
    { key: 'LineTotal', label: 'Thành tiền', className: 'w-[19.6%]', render: formatMoney },
  ]
  return <section aria-label="Chi tiết đơn hàng" className="flex min-w-0 flex-col gap-[18px]">
    <div className="flex min-h-[46px] items-center justify-between gap-3"><h2 className="m-0 text-xl font-bold">{order ? 'Đơn hàng #' + order.OrderCode : 'Chi tiết đơn hàng'}</h2><ProductButton secondary className="w-[100px] shrink-0 px-3!" disabled={busy} onClick={back}>← Quay lại</ProductButton></div>
    {notice && <p role="status" className="m-0 rounded-[10px] bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    {error && !intent && <p role="alert" className="m-0 rounded-[10px] bg-red-50 p-3 text-xs text-red-700">{error}</p>}
    {detail.loading ? <LoadingState label="Đang tải chi tiết đơn hàng…" /> : detail.error ? <ErrorState title="Không tải được đơn hàng" message={detail.error} onRetry={detail.refresh} /> : order && <>
      <div className="flex min-h-[70px] items-center justify-between gap-3 rounded-[14px] border border-admin-border bg-white px-[18px]"><div><p className="m-0 mb-[3px] text-[11px] leading-[normal] font-medium text-admin-muted">Trạng thái hiện tại</p><p className="m-0 text-base leading-[normal] font-semibold">{orderStatusLabel(order.OrderStatus)}</p></div><OrderBadge value={order.OrderStatus} className="leading-[normal]" /></div>
      <OrderProgress status={order.OrderStatus} />
      <div className="grid min-w-0 grid-cols-[minmax(0,720fr)_minmax(0,390fr)] items-start gap-[18px]">
        <div className="flex min-w-0 flex-col gap-4">
          <section aria-label="Thông tin đơn hàng" className={CARD + ' min-h-[178px]'}><h3 className={TITLE}>Thông tin đơn hàng</h3>
            <dl className="mt-2.5 mb-0 flex justify-between gap-6"><div className="flex min-w-0 flex-col gap-2"><Info label="Mã đơn" strong>{order.OrderCode}</Info><Info label="Khách hàng">{order.ReceiverName}</Info></div><div className="flex min-w-0 flex-col gap-2"><Info label="Ngày đặt">{formatDate(order.OrderedAt)}</Info><Info label="Số điện thoại">{order.ReceiverPhone}</Info></div></dl>
          </section>
          <section aria-label="Sản phẩm trong đơn" className={CARD + ' admin-table-inset min-h-[250px]'}><h3 className={TITLE + ' mb-2.5'}>Sản phẩm trong đơn</h3>
            <AdminTable variant="products" columns={columns} rows={order.Items ?? []} rowKey="OrderItemId" label="Sản phẩm trong đơn" emptyText="Đơn hàng chưa có sản phẩm." className="min-w-[570px] table-fixed [&_th]:h-[38px]! [&_th]:font-semibold! [&_td]:h-[58px]! [&_td]:py-2" />
          </section>
          <section aria-label="Lịch sử trạng thái" className={CARD + ' min-h-[230px]'}><h3 className={TITLE + ' mb-2.5'}>Lịch sử trạng thái</h3>
            {order.StatusHistories?.length ? <ol className="m-0 flex list-none flex-col gap-2.5 p-0">{order.StatusHistories.map((entry) => <li key={entry.OrderStatusHistoryId} className="flex items-start gap-3.5">
              <img src={historyDot} width="8" height="8" alt="" className="mt-1 shrink-0" />
              <div className="min-w-0"><p className="m-0 text-[11px] leading-normal font-medium break-words">{entry.OldStatus ? orderStatusLabel(entry.OldStatus) + ' → ' : 'Đơn hàng được tạo — '}{orderStatusLabel(entry.NewStatus)}</p><time dateTime={entry.ChangedAt} className="mt-0.5 block text-[10px] leading-normal text-admin-muted">{formatDateTime(entry.ChangedAt)}</time>{entry.Note && <p className="mt-1 mb-0 text-[11px] break-words whitespace-pre-wrap text-admin-muted">{entry.Note}</p>}</div>
            </li>)}</ol> : <p className="m-0 text-xs text-admin-muted">Chưa có lịch sử trạng thái.</p>}
          </section>
          {needsSerials && <section aria-label="Serial/IMEI của đơn" className={CARD + ' flex flex-col gap-3'}><h3 className={TITLE}>Serial/IMEI của đơn</h3>
            {serials.loading ? <LoadingState label="Đang tải Serial/IMEI…" /> : serials.error ? <ErrorState message={serials.error} onRetry={serials.refresh} /> : <>
              {serialItems.filter((item) => item.IsSerialTracked).map((item) => <SerialRow key={item.OrderItemId} item={item} busy={busy} editable={canUpdate && order.OrderStatus === 'Processing'} onAssign={assign} onRelease={(number) => write((token) => releaseOrderSerial(token, orderId, number), () => { serials.refresh(); setNotice('Đã gỡ Serial/IMEI.'); setCollected(false) })} />)}
              {!serialItems.some((item) => item.IsSerialTracked) && <p className="m-0 text-xs text-admin-muted">Các sản phẩm trong đơn không yêu cầu quản lý Serial/IMEI.</p>}
            </>}
          </section>}
        </div>
        <aside aria-label="Xử lý đơn hàng" className="flex min-w-0 flex-col gap-4">
          <section aria-label="Cập nhật trạng thái" className={CARD + ' flex min-h-[221px] flex-col items-start gap-3 py-[18px]'}><h3 className={TITLE}>Cập nhật trạng thái</h3><p className="m-0 text-[11px] leading-[normal] font-medium text-admin-muted">Trạng thái hiện tại</p><OrderBadge value={order.OrderStatus} className="leading-[normal]" />
            {canUpdate ? <>
              {next && <ProductButton disabled={busy} onClick={() => choose('advance')}>{next[1]}</ProductButton>}
              {canCancelOrder(order) && <ProductButton secondary className="min-w-[110px] border-admin-red! text-admin-red! enabled:hover:bg-red-50!" disabled={busy} onClick={() => choose('cancel')}>Hủy đơn</ProductButton>}
              {!next && <p className="m-0 text-xs text-admin-muted">{order.OrderStatus === 'Cancelled' ? 'Đơn hàng đã đóng.' : 'Đơn hàng đã hoàn tất.'}</p>}
            </> : <p className="m-0 text-xs text-admin-muted">Bạn có quyền xem đơn hàng.</p>}
          </section>
          <details className={CARD} open={extraOpen} onToggle={(event) => setExtraOpen(event.currentTarget.open)}><summary className="cursor-pointer text-xs font-semibold text-admin-blue">Giao hàng, thanh toán & ghi chú</summary><div className="mt-4 flex flex-col gap-4">
            <dl className="m-0 flex flex-col gap-4"><Info label="Địa chỉ giao hàng">{order.ShippingAddress}</Info><Info label="Ghi chú khách hàng">{order.CustomerNote}</Info><Info label="Thanh toán">{PAYMENT_LABELS[order.PaymentStatus] ?? order.PaymentStatus}</Info><Info label="Phương thức thanh toán">{payment.loading ? 'Đang tải…' : payment.data?.Name ?? 'Chưa tải được'}</Info>{order.CancelReason && <Info label="Lý do hủy">{order.CancelReason}</Info>}</dl>
            {payment.error && <ErrorState title="Chưa tải được phương thức thanh toán" message={payment.error} onRetry={payment.refresh} className="py-2" />}
            <dl className="m-0 grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]"><dt className="text-admin-muted">Tiền hàng</dt><dd className="m-0 text-right">{formatMoney(order.Subtotal)}</dd><dt className="text-admin-muted">Phí vận chuyển</dt><dd className="m-0 text-right">{formatMoney(order.ShippingFee)}</dd><dt className="text-admin-muted">Giảm giá đơn hàng</dt><dd className="m-0 text-right">{formatMoney(order.DiscountAmount)}</dd><dt className="border-t border-admin-border pt-2 font-semibold">Tổng thanh toán</dt><dd className="m-0 border-t border-admin-border pt-2 text-right font-semibold text-admin-blue">{formatMoney(order.TotalAmount)}</dd></dl>
            {canUpdate ? <InternalNote key={order.InternalNote ?? ''} order={order} busy={busy} onSave={(value) => write((token) => updateOrderNote(token, orderId, { InternalNote: value }), () => { detail.refresh(); setNotice('Đã lưu ghi chú nội bộ.') })} /> : <dl className="m-0"><Info label="Ghi chú nội bộ">{order.InternalNote}</Info></dl>}
          </div></details>
        </aside>
      </div>
      <OrderStatusModal workflow={workflow} />
    </>}
  </section>
}
