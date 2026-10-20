import { useEffect, useRef, useState } from 'react'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { formatDateTime, formatMoney } from '../../lib/format.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { purchaseDeletable, purchaseEditable, purchaseReceivable, purchaseReceiveBody, variantLabel } from '../lib/purchases.js'
import { deletePurchase, closePurchase, decidePurchase, receivePurchase, resubmitPurchase } from '../services/purchases.js'
import AdminTable from './AdminTable.jsx'
import Modal from './Modal.jsx'
import { PRODUCT_CONTROL } from './ProductUi.jsx'
import { PurchaseButton, PurchaseStatus } from './PurchaseUi.jsx'
import PurchaseConfirmation from './PurchaseConfirmation.jsx'

function PoField({ label, children, className = '' }) {
  return <label className={'flex min-w-0 flex-col gap-1.5 text-xs font-semibold ' + className}>{label}{children}</label>
}
export function ReceiveForm({ po, variants, busy, run, onError }) {
  const [values, setValues] = useState({})
  const [note, setNote] = useState('')
  return <form className="flex flex-col gap-4" onSubmit={async (event) => {
    event.preventDefault()
    let body
    try { body = purchaseReceiveBody(po, values, variants.data ?? [], note) } catch (error) { onError(error.message); return }
    const result = await run((token) => receivePurchase(token, po.PurchaseOrderId, body), 'update', 'Đã ghi nhận hàng thực nhận.')
    if (result) { setValues({}); setNote('') }
  }}>
    <p className="m-0 text-xs text-admin-muted">Nhập số lượng thực nhận trong lần này; có thể nhận từng phần. Chỉ xác nhận sau khi kiểm đếm hàng và Serial/IMEI thực tế.</p>
    {po.Items.filter((item) => item.ReceivedQuantity < item.OrderedQuantity).map((item) => {
      const variant = variants.data?.find((entry) => entry.ProductVariantId === item.ProductVariantId)
      const value = values[item.PurchaseOrderItemId] ?? { Quantity: '', SerialNumbers: '' }
      function change(key, text) { setValues((previous) => ({ ...previous, [item.PurchaseOrderItemId]: { ...value, [key]: text } })) }
      return <div key={item.PurchaseOrderItemId} className="flex flex-col gap-3 rounded-xl border border-admin-border p-3"><strong className="text-xs">{variant ? variantLabel(variant) : 'Biến thể chưa tải được'} — Còn thiếu {item.OrderedQuantity - item.ReceivedQuantity}</strong><PoField label="Số lượng thực nhận"><input aria-label={'Số lượng thực nhận ' + (variant?.Sku ?? item.PurchaseOrderItemId)} type="number" min="0" max={item.OrderedQuantity - item.ReceivedQuantity} step="1" disabled={busy} className={PRODUCT_CONTROL} value={value.Quantity} onChange={(event) => change('Quantity', event.target.value)} /></PoField>{variant?.IsSerialTracked && <PoField label="Serial/IMEI"><textarea aria-label={'Serial/IMEI ' + variant.Sku} className={PRODUCT_CONTROL} rows={3} disabled={busy} placeholder="Mỗi sản phẩm một mã, mỗi mã một dòng" maxLength={50000} value={value.SerialNumbers} onChange={(event) => change('SerialNumbers', event.target.value)} /></PoField>}</div>
    })}
    <PoField label="Ghi chú nhận hàng"><textarea aria-label="Ghi chú nhận hàng" className={PRODUCT_CONTROL} maxLength={4000} rows={2} disabled={busy} value={note} onChange={(event) => setNote(event.target.value)} /></PoField><PurchaseButton type="submit" disabled={busy || variants.loading || Boolean(variants.error)} className="self-end">Xác nhận thực nhận</PurchaseButton>
  </form>
}

export default function PurchaseDialog({ mode, purchaseId, suppliers, variants, creatorNames, onClose, onDone, onChanged }) {
  const auth = useInternalAuth()
  const can = (action) => auth.permissions.includes('purchases:' + action)
  const permitted = mode === 'delete' ? can('delete') && auth.user.Role === 'Admin' : mode === 'view' && can('view')
  const detail = useAdminQuery('/admin/purchase-orders/' + encodeURIComponent(purchaseId ?? ''), {}, permitted)
  const [saved, setSaved] = useState(null)
  const po = saved ?? detail.data
  const [action, setAction] = useState(mode === 'delete' ? 'delete' : '')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const writing = useRef(false), mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const receipts = useAdminQuery('/admin/purchase-orders/' + encodeURIComponent(purchaseId ?? '') + '/receipts', {}, permitted && mode === 'view' && Boolean(po) && auth.permissions.includes('purchase_history:view'))
  async function run(call, permission, message) {
    if (!can(permission) || writing.current) return null
    writing.current = true; setBusy(true); setError(''); setNotice('')
    try {
      const result = await auth.withAccessToken(call)
      if (mounted.current) { if (result?.PurchaseOrderId) setSaved(result); if (message) { setNotice(message); onChanged(message, result) } }
      return mounted.current ? result : null
    } catch (failure) { if (mounted.current) setError(failure.message); return null }
    finally { writing.current = false; if (mounted.current) setBusy(false) }
  }
  function choose(value) { setAction(value); setReason(''); setError('') }
  const canDecide = po && can('update') && auth.user.Role === 'Admin' && po.Status === 'Pending' && po.CreatedByUserId !== auth.user.UserId
  async function confirm(event, enteredReason = reason) {
    event?.preventDefault()
    if (!po) return
    if (['reject', 'close'].includes(action) && !enteredReason.trim()) { setError('Vui lòng nhập lý do.'); return }
    let result
    if (action === 'delete' && purchaseDeletable(po, auth.user)) {
      result = await run(async (token) => { await deletePurchase(token, po.PurchaseOrderId); return true }, 'delete', '')
      if (result) onDone('Đã xóa phiếu nhập.')
      return
    }
    if (action === 'approve' && canDecide) result = await run((token) => decidePurchase(token, po.PurchaseOrderId, { Status: 'Approved' }), 'update', 'Đã xác nhận phiếu nhập.')
    if (action === 'reject' && canDecide) result = await run((token) => decidePurchase(token, po.PurchaseOrderId, { Status: 'Rejected', RejectReason: enteredReason.trim() }), 'update', 'Đã từ chối phiếu nhập.')
    if (action === 'resubmit' && po.Status === 'Rejected' && purchaseEditable(po, auth.user)) result = await run((token) => resubmitPurchase(token, po.PurchaseOrderId), 'update', 'Đã gửi lại phiếu chờ duyệt.')
    if (action === 'close' && auth.user.Role === 'Admin' && po.Status === 'Receiving') result = await run((token) => closePurchase(token, po.PurchaseOrderId, { Reason: enteredReason.trim() }), 'update', 'Đã đóng phiếu nhận thiếu.')
    if (result) { choose(''); receipts.refresh() }
  }
  if (!permitted) return null
  if (['approve', 'reject', 'delete'].includes(action)) return <PurchaseConfirmation action={action} po={po} busy={busy} error={error} loading={detail.loading} loadError={detail.error} onRetry={detail.refresh} permitted={action === 'delete' ? can('delete') && purchaseDeletable(po, auth.user) : Boolean(canDecide)} onCancel={mode === 'delete' ? onClose : () => choose('')} onConfirm={(reason) => confirm(null, reason)} />
  const title = { view: 'Chi tiết phiếu nhập', delete: 'Xóa phiếu nhập' }[mode]
  const byId = new Map((variants.data ?? []).map((variant) => [variant.ProductVariantId, variant]))
  const supplierName = suppliers.data?.find((item) => item.SupplierId === po?.SupplierId)?.Name
  const columns = [
    { key: 'ProductVariantId', label: 'Sản phẩm / SKU', render: (id) => <span className="break-words">{byId.has(id) ? variantLabel(byId.get(id)) : 'Chưa có thông tin biến thể'}</span> },
    { key: 'OrderedQuantity', label: 'SL đặt' }, { key: 'ReceivedQuantity', label: 'Đã nhận' }, { key: 'MissingQuantity', label: 'Còn thiếu', render: (_, item) => item.OrderedQuantity - item.ReceivedQuantity },
    { key: 'UnitPrice', label: 'Giá nhập', render: formatMoney }, { key: 'LineTotal', label: 'Thành tiền', render: formatMoney },
  ]
  return <Modal open variant="tailwind" wide title={title} description={po?.PurchaseOrderCode} busy={busy} onClose={onClose} footer={<PurchaseButton secondary disabled={busy} onClick={onClose}>Đóng</PurchaseButton>}>
    {error && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-xs text-red-700">{error}</p>}{notice && <p role="status" className="mb-4 rounded-lg bg-green-50 p-3 text-xs text-green-700">{notice}</p>}
    {suppliers.error && <ErrorState message={suppliers.error} onRetry={suppliers.refresh} className="py-2" />}{variants.error && <ErrorState message={variants.error} onRetry={variants.refresh} className="py-2" />}
    {detail.loading ? <LoadingState label="Đang tải phiếu nhập…" /> : detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} /> : po && <div className="flex flex-col gap-4">
      <dl className="m-0 grid grid-cols-2 gap-3 rounded-xl bg-admin-page p-4 text-xs"><dt>Trạng thái</dt><dd className="m-0"><PurchaseStatus status={po.Status} /></dd><dt>Nhà cung cấp</dt><dd className="m-0 break-words">{supplierName ?? '—'}</dd><dt>Người tạo</dt><dd className="m-0">{creatorNames[po.CreatedByUserId] ?? '—'}</dd><dt>Ngày lập</dt><dd className="m-0">{formatDateTime(po.CreatedAt)}</dd><dt>Tổng tiền</dt><dd className="m-0 font-semibold text-admin-blue">{formatMoney(po.TotalAmount)}</dd>{po.Note && <><dt>Ghi chú</dt><dd className="m-0 break-words whitespace-pre-wrap">{po.Note}</dd></>}{po.RejectReason && <><dt>Lý do từ chối</dt><dd className="m-0 break-words">{po.RejectReason}</dd></>}{po.CloseReason && <><dt>Lý do đóng phiếu</dt><dd className="m-0 break-words">{po.CloseReason}</dd></>}</dl>
      {<AdminTable columns={columns} rows={po.Items} rowKey="PurchaseOrderItemId" label="Sản phẩm trong phiếu nhập" className="[&_td]:py-3" />}
      {action === 'receive' && purchaseReceivable(po) && can('update') ? <ReceiveForm key={po.Status + '-' + po.Items.map((item) => item.ReceivedQuantity).join('-')} po={po} variants={variants} busy={busy} run={async (...args) => { const result = await run(...args); if (result) { choose(''); receipts.refresh() } return result }} onError={setError} /> : action && <form className="flex flex-col gap-3 rounded-xl border border-admin-border p-4" onSubmit={confirm}>
        <p className="m-0 text-sm font-semibold">{{ approve: 'Xác nhận duyệt phiếu này?', reject: 'Từ chối phiếu nhập', resubmit: 'Gửi lại phiếu để Admin duyệt?', close: 'Đóng phiếu và giữ nguyên số lượng đã nhận?' }[action]}</p>
        {action === 'close' && <p className="m-0 text-xs text-admin-muted">Phần còn thiếu sẽ không được tính là đã nhận và không được cộng vào tồn kho.</p>}
        {['reject', 'close'].includes(action) && <PoField label="Lý do"><textarea aria-label="Lý do" required disabled={busy} className={PRODUCT_CONTROL} rows={3} maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} /></PoField>}
        <div className="flex justify-end gap-2"><PurchaseButton secondary disabled={busy} onClick={() => choose('')}>Quay lại</PurchaseButton><PurchaseButton type="submit" disabled={busy || (['reject', 'close'].includes(action) && !reason.trim())}>Xác nhận</PurchaseButton></div>
      </form>}
      {!action && <div className="flex flex-wrap gap-2">
        {canDecide && <><PurchaseButton disabled={busy} onClick={() => choose('approve')}>Duyệt phiếu</PurchaseButton><PurchaseButton secondary disabled={busy} onClick={() => choose('reject')}>Từ chối phiếu</PurchaseButton></>}
        {can('update') && po.Status === 'Rejected' && purchaseEditable(po, auth.user) && <PurchaseButton disabled={busy} onClick={() => choose('resubmit')}>Gửi lại để duyệt</PurchaseButton>}
        {can('update') && purchaseReceivable(po) && <PurchaseButton disabled={busy} onClick={() => choose('receive')}>Nhận hàng vào kho</PurchaseButton>}
        {can('update') && auth.user.Role === 'Admin' && po.Status === 'Receiving' && <PurchaseButton secondary disabled={busy} onClick={() => choose('close')}>Đóng phiếu nhận thiếu</PurchaseButton>}
        {can('delete') && purchaseDeletable(po, auth.user) && <PurchaseButton secondary disabled={busy} onClick={() => choose('delete')}>Xóa phiếu</PurchaseButton>}
      </div>}
      {mode === 'view' && auth.permissions.includes('purchase_history:view') && <section aria-label="Lịch sử nhận hàng"><h3 className="mb-3 text-sm font-semibold">Lịch sử nhận hàng</h3>{receipts.loading ? <LoadingState label="Đang tải lịch sử nhận hàng…" /> : receipts.error ? <ErrorState message={receipts.error} onRetry={receipts.refresh} /> : receipts.data?.length ? <ol className="m-0 flex list-none flex-col gap-3 p-0">{receipts.data.map((receipt) => <li key={receipt.PurchaseReceiptId} className="rounded-lg border border-admin-border p-3 text-xs"><p className="m-0 font-semibold">{formatDateTime(receipt.ReceivedAt)} — {receipt.Items.reduce((sum, item) => sum + item.Quantity, 0)} sản phẩm</p>{receipt.Items.map((item) => <p key={item.PurchaseOrderItemId} className="mt-1 mb-0 text-admin-muted">{byId.has(po.Items.find((line) => line.PurchaseOrderItemId === item.PurchaseOrderItemId)?.ProductVariantId) ? variantLabel(byId.get(po.Items.find((line) => line.PurchaseOrderItemId === item.PurchaseOrderItemId).ProductVariantId)) : 'Sản phẩm trong phiếu'}: {item.Quantity} × {formatMoney(item.UnitPrice)}</p>)}{receipt.Note && <p className="mt-1 mb-0 whitespace-pre-wrap">{receipt.Note}</p>}</li>)}</ol> : <p className="m-0 text-xs text-admin-muted">Chưa có lần nhận hàng nào.</p>}</section>}
    </div>}
  </Modal>
}
