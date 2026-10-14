import { useEffect, useId, useRef } from 'react'

// A native modal dialog: focus trap, Escape and backdrop come from the browser.
// `busy` blocks closing while a request is running.
export default function Modal({ open, title, description, onClose, busy = false, wide = false, children, footer, variant, className = '' }) {
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

  const confirmation = variant === 'purchase-confirm'
  const review = ['review-detail', 'review-delete', 'review-error'].includes(variant)
  const productDelete = variant === 'product-delete'
  const productSave = variant === 'product-save'
  const productConfirmation = productDelete || productSave
  const compact = confirmation || review || productConfirmation
  const tailwind = variant === 'tailwind' || compact
  const padding = productSave ? 'px-4 pt-[37px] pb-[22px]' : productDelete ? 'px-4 pt-10 pb-[34px]' : variant === 'review-detail' ? 'p-[22px]' : variant === 'review-error' ? 'p-7' : 'p-6 max-sm:p-4'
  const headingGap = productSave ? 'mb-[28px]' : productDelete ? 'mb-[25px]' : variant === 'review-detail' ? 'mb-3' : variant === 'review-error' ? 'mb-2.5' : compact ? 'mb-3.5' : 'mb-5'
  const titleClass = productSave ? 'mx-auto my-0 w-[243px] text-center text-xl leading-6 font-bold' : productDelete ? 'm-0 text-center text-xl leading-6 font-bold' : variant === 'review-error' ? 'm-0 text-[15px] leading-[18px] font-semibold text-admin-red' : compact ? 'm-0 text-[17px] leading-[21px] font-bold break-words' : 'm-0 text-xl font-bold'
  return <dialog ref={dialog} className={(tailwind ? `fixed inset-0 m-auto max-h-[90dvh] max-w-[calc(100vw-32px)] ${productConfirmation ? 'border-0' : 'border border-admin-border'} bg-white p-0 font-admin text-admin-text backdrop:bg-black/40 backdrop:backdrop-blur-[2px] ${productConfirmation ? 'rounded-xl shadow-[0px_6px_16px_0px_rgba(0,0,0,0.18)]' : compact ? 'rounded-xl ' + (variant === 'review-error' ? '' : 'shadow-[0px_8px_24px_0px_rgba(0,0,0,0.14)]') : 'rounded-2xl shadow-xl ' + (wide ? 'w-[800px]' : 'w-[540px]')}` : `admin-modal ${wide ? 'is-wide' : ''}`) + ' ' + className} aria-labelledby={titleId}
    onCancel={(event) => { event.preventDefault(); requestClose() }}
    onClick={(event) => { if (event.target === dialog.current) requestClose() }}>
    {open && <div className={tailwind ? padding : 'admin-modal-inner'}>
      <div className={tailwind ? headingGap : 'admin-modal-head'}>
        <h2 id={titleId} className={tailwind ? titleClass : undefined}>{title}</h2>
        {description && <p className={tailwind ? 'mt-2 text-xs text-admin-muted' : undefined}>{description}</p>}
      </div>
      <div className={tailwind ? 'text-sm' : 'admin-modal-body'}>{children}</div>
      {footer && <div className={tailwind ? 'mt-5 flex flex-wrap justify-end gap-2 border-t border-admin-border pt-4' : 'admin-modal-footer'}>{footer}</div>}
    </div>}
  </dialog>
}
