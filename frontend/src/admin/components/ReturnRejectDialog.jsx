import { useState } from 'react'
import Modal from './Modal.jsx'
import { ReturnButton } from './ReturnUi.jsx'

export default function ReturnRejectDialog({ open, busy, error, onClose, onSubmit }) {
  const [reason, setReason] = useState(''), [invalid, setInvalid] = useState('')
  return <Modal open={open} title="Từ chối yêu cầu đổi trả" onClose={onClose} busy={busy} variant="tailwind">
    <form className="flex flex-col gap-4" onSubmit={(event) => {
      event.preventDefault()
      if (!reason.trim()) { setInvalid('Vui lòng nhập lý do từ chối.'); return }
      setInvalid(''); onSubmit(reason.trim())
    }}>
      <label className="flex flex-col gap-2 text-xs font-medium">Lý do từ chối<textarea autoFocus aria-label="Lý do từ chối" className="min-h-28 w-full resize-y rounded-lg border border-admin-border bg-white p-3 text-xs font-normal" maxLength={4000} value={reason} disabled={busy} onChange={(event) => { setReason(event.target.value); setInvalid('') }} /></label>
      {(invalid || error) && <p role="alert" className="m-0 text-xs text-admin-red">{invalid || error}</p>}
      <div className="flex justify-end gap-2"><ReturnButton secondary className="text-admin-text!" disabled={busy} onClick={onClose}>Đóng</ReturnButton><ReturnButton type="submit" disabled={busy} className="border-admin-red! bg-admin-red!">{busy ? 'Đang xử lý…' : 'Xác nhận từ chối'}</ReturnButton></div>
    </form>
  </Modal>
}
