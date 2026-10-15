import Modal from './Modal.jsx'
import { ReturnButton } from './ReturnUi.jsx'
import { WarrantyButton } from './WarrantyUi.jsx'

export default function ServiceRequestActions({ workflow, warranty = false }) {
  const { item, closed, canUpdate, busy, error, notice, rejecting, advance, chooseReject, refresh } = workflow
  const Button = warranty ? WarrantyButton : ReturnButton
  if (!item) return null
  const initial = warranty ? workflow.stage === 'New' : item.Status === 'Pending'
  const resultIncomplete = warranty && workflow.stage === 'Repairing' && (!workflow.resultType || !workflow.resultNote.trim())
  return <>
    <div aria-label="Thao tác phiếu" className="flex min-h-[33px] items-center justify-end gap-2 pr-3.5">
      {notice && <span role="status" className="mr-auto text-[11px] text-admin-muted">{notice}</span>}
      {closed ? <span className="text-xs font-semibold text-admin-muted">Đóng phiếu</span> : canUpdate && <>
        <Button secondary className="border-admin-red! text-admin-red!" disabled={busy} onClick={chooseReject}>Từ chối</Button>
        <Button disabled={busy || resultIncomplete} onClick={advance}>{busy ? 'Đang xử lý…' : initial ? warranty ? 'Tiếp nhận & kiểm tra' : 'Tiếp nhận yêu cầu' : 'Giai đoạn kế tiếp'}</Button>
      </>}
    </div>
    <Modal open={Boolean(error && !rejecting)} title="Không cập nhật được phiếu" onClose={workflow.clearError} busy={busy} variant="tailwind" footer={<><Button secondary className="text-admin-text!" onClick={workflow.clearError}>Đóng</Button><Button onClick={refresh}>Tải lại phiếu</Button></>}><p role="alert" className="m-0 text-xs text-admin-red">{error}</p></Modal>
  </>
}
