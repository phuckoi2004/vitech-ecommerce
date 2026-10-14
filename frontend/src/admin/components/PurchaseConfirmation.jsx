import { useState } from 'react'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import Modal from './Modal.jsx'
import { PurchaseButton } from './PurchaseUi.jsx'

// Figma confirmations share a layout, while their API actions remain explicit at the call site.
export default function PurchaseConfirmation({ action, po, busy, error, loading = false, loadError = '', onRetry, permitted, onCancel, onConfirm }) {
  const [reason, setReason] = useState('')
  const rejection = action === 'reject', deleting = action === 'cancel'
  const title = rejection ? 'Từ chối phiếu nhập' + (po ? ' ' + po.PurchaseOrderCode : '') : deleting ? 'Xóa phiếu nhập?' : 'Xác nhận phiếu nhập' + (po ? ' ' + po.PurchaseOrderCode : '') + '?'
  const confirmLabel = rejection ? 'Xác nhận từ chối' : deleting ? 'Xác nhận xóa' : 'Xác nhận phiếu'
  const disabled = busy || loading || Boolean(loadError) || !po || !permitted || (rejection && !reason.trim())
  return <Modal open variant="purchase-confirm" title={title} className={rejection ? 'w-[480px] min-h-[330px]' : deleting ? 'w-[460px] min-h-[260px]' : 'w-[460px] min-h-[270px]'} busy={busy} onClose={onCancel}>
    <form className="flex min-w-0 flex-col gap-3.5" onSubmit={(event) => { event.preventDefault(); if (!disabled) onConfirm(reason.trim()) }}>
      {error && <p role="alert" className="m-0 rounded-lg bg-red-50 p-3 text-xs text-red-700">{error}</p>}
      {loading ? <LoadingState label="Đang tải phiếu nhập…" className="py-2" /> : loadError ? <ErrorState message={loadError} onRetry={onRetry} className="py-2" /> : rejection ? <label className="flex min-w-0 flex-col gap-[5px] text-[10px] leading-3 font-medium">Lý do từ chối<input aria-label="Lý do từ chối" type="text" required autoFocus maxLength={2000} placeholder="Nhập lý do từ chối phiếu nhập" className="h-10 w-full rounded-lg border border-admin-border bg-white px-[11px] text-[10px] font-normal text-admin-text placeholder:text-admin-muted disabled:opacity-60" value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} /></label> : <p className="m-0 text-[11px] leading-[13px] text-admin-muted">{deleting ? <>Phiếu{po ? ' ' + po.PurchaseOrderCode : ''} sẽ chuyển sang trạng thái “Đã hủy” và giữ lại lịch sử. Chỉ hủy được phiếu chưa nhận hàng.</> : 'Phiếu nhập sẽ chuyển từ trạng thái “Chờ xác nhận” sang “Đã xác nhận”.'}</p>}
      {deleting && po && !permitted && !loading && !loadError && <p role="alert" className="m-0 text-[11px] text-admin-red">Phiếu đã nhận hàng hoặc đã kết thúc không thể hủy.</p>}
      <div className="flex justify-end gap-0"><PurchaseButton secondary disabled={busy} onClick={onCancel}>Hủy</PurchaseButton><PurchaseButton type="submit" secondary={rejection || deleting} disabled={disabled} className={rejection || deleting ? 'border-admin-red! enabled:hover:bg-red-50!' : 'border-admin-red! bg-admin-red! enabled:hover:bg-admin-red/90!'}><span className={rejection || deleting ? 'text-admin-red' : 'text-white'}>{busy ? 'Đang xử lý…' : confirmLabel}</span></PurchaseButton></div>
    </form>
  </Modal>
}
