import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import { formatDateTime, formatMoney } from '../../lib/format.js'
import AdminTable from '../components/AdminTable.jsx'
import PurchaseActionModal from '../components/PurchaseActionModal.jsx'
import PurchaseDialog from '../components/PurchaseDialogs.jsx'
import { PurchaseButton, PurchaseStatus } from '../components/PurchaseUi.jsx'
import usePurchaseDetail from '../hooks/usePurchaseDetail.js'
import { PURCHASE_STATUSES, purchaseCancellable, purchaseEditable, purchaseListSearch, purchaseReceivable, variantLabel } from '../lib/purchases.js'

const DESCRIPTIONS = {
  Pending: 'Phiếu đang chờ quản trị viên xác nhận', Approved: 'Phiếu đã được xác nhận, có thể nhận hàng vào kho',
  Rejected: 'Phiếu bị từ chối, có thể chỉnh sửa và gửi lại để duyệt', Receiving: 'Phiếu đang nhận hàng từng phần',
  Completed: 'Phiếu đã nhận đủ số lượng đặt', Cancelled: 'Phiếu đã hủy, thông tin được giữ lại để tra cứu', Closed: 'Phiếu đã đóng, giữ nguyên số lượng thực nhận',
}
const CARD = 'min-w-0 min-h-[245px] rounded-xl border border-admin-border bg-white p-4'
const TITLE = 'm-0 text-[13px] leading-4 font-semibold'

function Info({ label, children }) {
  return <div className="grid grid-cols-[170px_minmax(0,1fr)] gap-0 text-[10px] leading-3"><dt className="font-medium text-admin-muted">{label}</dt><dd className="m-0 min-w-0 break-words whitespace-pre-wrap">{children ?? '—'}</dd></div>
}

export default function PurchaseDetailPage() {
  const { purchaseId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const action = params.get('dialog') ?? ''
  const workflow = usePurchaseDetail(purchaseId, false, location.state?.purchaseNotice ?? '')
  const { auth, can, detail, po, suppliers, variants, users, names, receipts, showHistory, busy, error, notice, setError, refresh } = workflow
  const canDecide = Boolean(po && can('update') && auth.user.Role === 'Admin' && po.Status === 'Pending' && po.CreatedByUserId !== auth.user.UserId)
  const allowed = {
    edit: can('update'), cancel: can('delete') && po && purchaseCancellable(po), approve: canDecide, reject: canDecide,
    resubmit: can('update') && po?.Status === 'Rejected', receive: can('update') && po && purchaseReceivable(po), close: can('update') && auth.user.Role === 'Admin' && po?.Status === 'Receiving',
  }
  function choose(value) {
    if (busy) return
    if (value === 'edit') { navigate('/admin/purchases/' + encodeURIComponent(purchaseId) + '/edit' + purchaseListSearch(params)); return }
    setError('')
    setParams((previous) => { const next = new URLSearchParams(previous); next.delete('purchase'); if (value) next.set('dialog', value); else next.delete('dialog'); return next })
  }
  const byId = new Map(variants.data.map((variant) => [variant.ProductVariantId, variant]))
  const account = (id) => id ? names[id] ?? 'ID: ' + id : '—'
  const columns = [
    { key: 'ProductVariantId', label: 'Sản phẩm / biến thể', className: 'w-[26.60%]', render: (id) => <span className="break-words">{byId.has(id) ? [byId.get(id).Name, byId.get(id).VariantName].filter(Boolean).join(' - ') || byId.get(id).Sku : variants.loading ? 'Đang tải sản phẩm…' : 'ID biến thể: ' + id}</span> },
    { key: 'OrderedQuantity', label: 'SL đặt', className: 'w-[9.75%]' },
    { key: 'ReceivedQuantity', label: 'SL thực nhận', className: 'w-[9.75%]' },
    { key: 'UnitPrice', label: 'Đơn giá nhập', className: 'w-[12.41%]', render: formatMoney },
    { key: 'LineTotal', label: 'Thành tiền', className: 'w-[14.18%]', render: formatMoney },
    { key: 'Note', label: 'Ghi chú', className: 'w-[27.31%]', render: (note) => <span className="break-words whitespace-pre-wrap">{note || '—'}</span> },
  ]
  if (action === 'edit' && can('update')) return <Navigate replace to={'/admin/purchases/' + encodeURIComponent(purchaseId) + '/edit' + purchaseListSearch(params)} />
  return <section aria-label="Chi tiết phiếu nhập" className="-mt-1 flex min-w-0 flex-col gap-3.5">
    <div className="flex items-center gap-0"><div className="mr-auto"><h2 className="m-0 text-xl leading-6 font-bold">{po ? 'Phiếu nhập ' + po.PurchaseOrderCode : 'Chi tiết phiếu nhập'}</h2>{po && <p className="mt-[3px] mb-0 text-[11px] leading-[13px] text-admin-muted">{DESCRIPTIONS[po.Status] ?? PURCHASE_STATUSES[po.Status]}</p>}</div>{po && <PurchaseStatus status={po.Status} />}<PurchaseButton secondary className="shrink-0" disabled={busy} onClick={() => navigate('/admin/purchases' + purchaseListSearch(params))}>← Danh sách phiếu nhập</PurchaseButton></div>
    {notice && <p role="status" className="m-0 rounded-[9px] bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    {error && !action && <p role="alert" className="m-0 rounded-[9px] bg-red-50 p-3 text-xs text-red-700">{error}</p>}
    {detail.loading && !po ? <LoadingState label="Đang tải chi tiết phiếu nhập…" /> : detail.error && !po ? <ErrorState title="Không tải được phiếu nhập" message={detail.error} onRetry={detail.refresh} /> : po && <>
      {suppliers.error && <ErrorState title="Chưa tải được nhà cung cấp" message={suppliers.error} onRetry={suppliers.refresh} className="py-2" />}
      {variants.error && <ErrorState title="Chưa tải được sản phẩm" message={variants.error} onRetry={variants.refresh} className="py-2" />}
      {users.error && <ErrorState title="Chưa tải được tên tài khoản" message={users.error} onRetry={users.refresh} className="py-2" />}
      <div className="grid min-w-0 grid-cols-[minmax(0,420fr)_minmax(0,692fr)] items-start gap-4">
        <section aria-label="Thông tin phiếu nhập" className={CARD}><h3 className={TITLE}>Thông tin phiếu nhập</h3><dl className="mt-[9px] mb-0 flex flex-col gap-[9px]">
          <Info label="Mã phiếu">{po.PurchaseOrderCode}</Info><Info label="Nhà cung cấp">{suppliers.data?.find((supplier) => supplier.SupplierId === po.SupplierId)?.Name ?? (suppliers.loading ? 'Đang tải…' : '—')}</Info><Info label="Người tạo">{po.CreatedByName ?? account(po.CreatedByUserId)}</Info><Info label="Ngày lập phiếu">{formatDateTime(po.CreatedAt)}</Info><Info label="Ghi chú">{po.Note || '—'}</Info>
        </dl></section>
        <section aria-label="Xử lý của quản trị viên" className={CARD}><h3 className={TITLE}>Xử lý của quản trị viên</h3><dl className="mt-[9px] mb-0 flex flex-col gap-[9px]">
          <Info label="Trạng thái">{PURCHASE_STATUSES[po.Status] ?? po.Status}</Info><Info label="Người duyệt / từ chối">{account(po.DecidedByUserId)}</Info><Info label="Thời điểm xử lý">{formatDateTime(po.DecidedAt)}</Info><Info label="Lý do từ chối">{po.RejectReason || '—'}</Info><Info label="Tổng tiền">{formatMoney(po.TotalAmount)}</Info>
          {po.Status === 'Closed' && <><Info label="Người đóng phiếu">{account(po.ClosedByUserId)}</Info><Info label="Thời điểm đóng">{formatDateTime(po.ClosedAt)}</Info><Info label="Lý do đóng phiếu">{po.CloseReason || '—'}</Info></>}
        </dl></section>
      </div>
      <section aria-label="Chi tiết sản phẩm nhập" className="overflow-hidden rounded-xl border border-admin-border bg-white"><h3 className={TITLE + ' px-3.5 py-3'}>Chi tiết sản phẩm nhập</h3>
        <AdminTable columns={columns} rows={po.Items} rowKey="PurchaseOrderItemId" label="Sản phẩm trong phiếu nhập" emptyText="Phiếu nhập chưa có sản phẩm." className="table-fixed [&_th]:h-[52px]! [&_th]:border-b-0! [&_th]:pr-[7px]! [&_th]:pl-[9px]! [&_th]:text-[9px]! [&_th]:font-semibold! [&_td]:h-[52px]! [&_td]:pr-[7px]! [&_td]:pl-[9px]! [&_td]:text-[10px]! [&_td]:leading-[normal] [&_tr:last-child_td]:border-b-0" />
      </section>
      <div role="group" aria-label="Thao tác phiếu nhập" className="flex justify-end gap-0">
        {can('delete') && purchaseCancellable(po) && po.Status !== 'Pending' && <PurchaseButton secondary disabled={busy} onClick={() => choose('cancel')}>Hủy phiếu</PurchaseButton>}
        {can('update') && <PurchaseButton secondary disabled={busy || !purchaseEditable(po)} title={!purchaseEditable(po) ? 'Chỉ sửa phiếu chờ xác nhận hoặc bị từ chối' : undefined} onClick={() => choose('edit')}>Sửa phiếu</PurchaseButton>}
        {canDecide && <><PurchaseButton secondary className="border-admin-red! enabled:hover:bg-red-50!" disabled={busy} onClick={() => choose('reject')}><span className="text-admin-red">Từ chối</span></PurchaseButton><PurchaseButton disabled={busy} onClick={() => choose('approve')}>Xác nhận phiếu</PurchaseButton></>}
        {allowed.resubmit && <PurchaseButton disabled={busy} onClick={() => choose('resubmit')}>Gửi lại để duyệt</PurchaseButton>}
        {allowed.close && <PurchaseButton secondary disabled={busy} onClick={() => choose('close')}>Đóng phiếu nhận thiếu</PurchaseButton>}
        {allowed.receive && <PurchaseButton disabled={busy || variants.loading || Boolean(variants.error) || !auth.permissions.includes('products:view')} onClick={() => choose('receive')}>Nhận hàng vào kho</PurchaseButton>}
      </div>
      {showHistory && auth.permissions.includes('purchase_history:view') && <section aria-label="Lịch sử nhận hàng" className="rounded-xl border border-admin-border bg-white p-4"><h3 className={TITLE + ' mb-3'}>Lịch sử nhận hàng</h3>
        {receipts.loading ? <LoadingState label="Đang tải lịch sử nhận hàng…" /> : receipts.error ? <ErrorState message={receipts.error} onRetry={receipts.refresh} /> : receipts.data?.length ? <ol className="m-0 flex list-none flex-col gap-3 p-0">{receipts.data.map((receipt) => <li key={receipt.PurchaseReceiptId} className="border-b border-admin-border pb-3 text-[11px] last:border-0 last:pb-0"><p className="m-0 font-semibold">{formatDateTime(receipt.ReceivedAt)} — {receipt.Items.reduce((sum, item) => sum + item.Quantity, 0)} sản phẩm</p>{receipt.Items.map((item) => { const variant = byId.get(po.Items.find((line) => line.PurchaseOrderItemId === item.PurchaseOrderItemId)?.ProductVariantId); return <p key={item.PurchaseOrderItemId} className="mt-1 mb-0 break-words text-admin-muted">{variant ? variantLabel(variant) : 'ID dòng: ' + item.PurchaseOrderItemId}: {item.Quantity} × {formatMoney(item.UnitPrice)}</p> })}{receipt.Note && <p className="mt-1 mb-0 break-words whitespace-pre-wrap">{receipt.Note}</p>}</li>)}</ol> : <p className="m-0 text-xs text-admin-muted">Chưa có lần nhận hàng nào.</p>}
      </section>}
    </>}
    {po && allowed[action] && ['edit', 'cancel'].includes(action) && <PurchaseDialog key={action + '-' + purchaseId} mode={action} purchaseId={purchaseId} suppliers={suppliers} variants={variants} creatorNames={names} onClose={() => choose('')} onChanged={refresh} onDone={(message) => { refresh(message); choose('') }} />}
    {po && allowed[action] && ['approve', 'reject', 'resubmit', 'close', 'receive'].includes(action) && <PurchaseActionModal key={action + '-' + purchaseId} action={action} workflow={workflow} permitted={Boolean(allowed[action])} onClose={() => choose('')} />}
  </section>
}
