import { useState } from 'react'
import { closePurchase, decidePurchase, resubmitPurchase } from '../services/purchases.js'
import Modal from './Modal.jsx'
import { ReceiveForm } from './PurchaseDialogs.jsx'
import { PRODUCT_CONTROL } from './ProductUi.jsx'
import { PurchaseButton } from './PurchaseUi.jsx'
import PurchaseConfirmation from './PurchaseConfirmation.jsx'

const TITLES = { approve: 'Xác nhận phiếu nhập', reject: 'Từ chối phiếu nhập', resubmit: 'Gửi lại phiếu để duyệt', close: 'Đóng phiếu nhận thiếu', receive: 'Nhận hàng vào kho' }

export default function PurchaseActionModal({ action, workflow, onClose, permitted }) {
  const { po, variants, busy, error, run, setError } = workflow
  const [reason, setReason] = useState('')
  const requiresReason = ['reject', 'close'].includes(action)
  async function confirm(event, rejectionReason = reason) {
    event?.preventDefault()
    if (!permitted || busy) return
    if (requiresReason && !rejectionReason.trim()) { setError('Vui lòng nhập lý do.'); return }
    const messages = { approve: 'Đã xác nhận phiếu nhập.', reject: 'Đã từ chối phiếu nhập.', resubmit: 'Đã gửi lại phiếu chờ duyệt.', close: 'Đã đóng phiếu nhận thiếu.' }
    const call = (token) => action === 'close' ? closePurchase(token, po.PurchaseOrderId, { Reason: rejectionReason.trim() }) : action === 'resubmit' ? resubmitPurchase(token, po.PurchaseOrderId) : decidePurchase(token, po.PurchaseOrderId, action === 'reject' ? { Status: 'Rejected', RejectReason: rejectionReason.trim() } : { Status: 'Approved' })
    if (await run(call, 'update', messages[action])) onClose()
  }
  if (['approve', 'reject'].includes(action)) return <PurchaseConfirmation action={action} po={po} busy={busy} error={error} permitted={permitted} onCancel={onClose} onConfirm={(reason) => confirm(null, reason)} />
  return <Modal open variant="tailwind" wide={action === 'receive'} title={TITLES[action]} description={po.PurchaseOrderCode} busy={busy} onClose={onClose} footer={<PurchaseButton secondary disabled={busy} onClick={onClose}>Đóng</PurchaseButton>}>
    {error && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-xs text-red-700">{error}</p>}
    {action === 'receive' ? <ReceiveForm po={po} variants={variants} busy={busy} onError={setError} run={async (...args) => { if (!permitted) return null; const result = await run(...args); if (result) onClose(); return result }} /> : <form className="flex flex-col gap-4" onSubmit={confirm}>
      <p className="m-0 text-xs leading-relaxed text-admin-muted">{{ approve: 'Xác nhận duyệt phiếu nhập này? Việc nhận hàng vào kho được thực hiện ở bước tiếp theo.', reject: 'Nhập lý do từ chối để người lập phiếu kiểm tra và chỉnh sửa.', resubmit: 'Gửi lại phiếu nhập này để quản trị viên duyệt?', close: 'Đóng phiếu và giữ nguyên số lượng đã nhận. Phần còn thiếu sẽ không được cộng vào tồn kho.' }[action]}</p>
      {requiresReason && <label className="flex flex-col gap-1.5 text-xs font-semibold">Lý do<textarea aria-label="Lý do" required className={PRODUCT_CONTROL} rows={3} maxLength={2000} disabled={busy} value={reason} onChange={(event) => setReason(event.target.value)} /></label>}
      <PurchaseButton type="submit" className="self-end" disabled={!permitted || busy || (requiresReason && !reason.trim())}>{busy ? 'Đang xử lý…' : 'Xác nhận'}</PurchaseButton>
    </form>}
  </Modal>
}
