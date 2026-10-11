import { useEffect, useId, useRef } from 'react'

// A native modal dialog: focus trap, Escape and backdrop come from the browser.
// `busy` blocks closing while a request is running.
export default function Modal({ open, title, description, onClose, busy = false, wide = false, children, footer }) {
  const dialog = useRef(null)
  const titleId = useId()

  useEffect(() => {
    const element = dialog.current
    if (open && !element.open) element.showModal()
    if (!open && element.open) element.close()
  }, [open])

  function requestClose() {
    if (!busy) onClose()
  }

  return <dialog ref={dialog} className={`admin-modal ${wide ? 'is-wide' : ''}`} aria-labelledby={titleId}
    onCancel={(event) => { event.preventDefault(); requestClose() }}
    onClick={(event) => { if (event.target === dialog.current) requestClose() }}>
    {open && <div className="admin-modal-inner">
      <div className="admin-modal-head">
        <h2 id={titleId}>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      <div className="admin-modal-body">{children}</div>
      {footer && <div className="admin-modal-footer">{footer}</div>}
    </div>}
  </dialog>
}
