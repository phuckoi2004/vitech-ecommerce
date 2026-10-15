import { useEffect, useId, useRef } from 'react'

// Native dialog supplies Escape, a focus trap and return focus without a new dependency.
export default function ProductModal({ open, title, onClose, children, className = '' }) {
  const dialog = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const element = dialog.current
    if (open && !element.open) element.showModal()
    if (!open && element.open) element.close()
    return () => { if (element.open) element.close() }
  }, [open])

  return <dialog ref={dialog} className={`pd-modal ${className}`} aria-labelledby={titleId}
    onCancel={(event) => { event.preventDefault(); onClose() }}
    onClick={(event) => { if (event.target === dialog.current) onClose() }}>
    {open && <>
      <header className="pd-modal-heading"><h2 id={titleId}>{title}</h2>
        <button type="button" className="pd-close" aria-label="Đóng cửa sổ" onClick={onClose}>×</button>
      </header>
      {children}
    </>}
  </dialog>
}
