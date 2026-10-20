import { useEffect, useId, useRef, useState } from 'react'
import './ConsultationButton.css'

export default function ConsultationButton({ className = '', disabled = false, onStaff }) {
  const [open, setOpen] = useState(false)
  const dialog = useRef(null)
  const trigger = useRef(null)
  const employeeOption = useRef(null)
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    const element = dialog.current
    element.showModal()
    employeeOption.current?.focus()
    return () => {
      if (element.open) element.close()
    }
  }, [open])

  function close() {
    dialog.current?.close()
    setOpen(false)
    trigger.current?.focus()
  }

  function choose(kind) {
    // Release the modal's focus trap before opening the existing chat panel.
    dialog.current?.close()
    setOpen(false)
    if (kind === 'staff' && onStaff) { onStaff(); return }
    window.dispatchEvent(new Event(`vietech-open-${kind}-chat`))
  }

  return <>
    <button ref={trigger} type="button" className={`consultation-trigger ${className}`} disabled={disabled}
      aria-haspopup="dialog" onClick={() => setOpen(true)}>
      Tư vấn ngay
    </button>
    <dialog ref={dialog} className="consultation-dialog" aria-labelledby={titleId} aria-modal="true"
      onCancel={event => { event.preventDefault(); close() }}
      onClick={event => { if (event.target === dialog.current) close() }}>
      {open && <div className="consultation-inner">
        <header className="consultation-heading">
          <h2 id={titleId}>Chọn hình thức tư vấn</h2>
          <button type="button" className="consultation-close" aria-label="Đóng lựa chọn tư vấn" onClick={close}>×</button>
        </header>
        <div className="consultation-options">
          <button ref={employeeOption} type="button" onClick={() => choose('staff')}>Chat với nhân viên</button>
          <button type="button" onClick={() => choose('ai')}>Chat với AI</button>
        </div>
      </div>}
    </dialog>
  </>
}
