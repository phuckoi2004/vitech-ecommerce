import { useEffect, useId, useRef } from 'react'
import { Link } from 'react-router-dom'
import { LOGIN_PATH, REGISTER_PATH } from '../routes/paths.js'

const ACTION = 'inline-flex h-[53px] items-center justify-center rounded-[8px] px-3 text-base font-bold no-underline transition-colors '
  + 'focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brand-300'

// Figma "Bạn đã có tài khoản chưa?": asked when a visitor without an account adds to cart, buys now, opens
// the wishlist or starts a product consultation. Both choices keep `next`, so the visitor returns to the same
// page after signing in.
export default function LoginPromptDialog({ open, next, onClose }) {
  const dialog = useRef(null), login = useRef(null)
  const titleId = useId()
  const query = next ? `?next=${encodeURIComponent(next)}` : ''

  useEffect(() => {
    const element = dialog.current
    if (open && !element.open) {
      element.showModal()
      login.current?.focus()
    }
    if (!open && element.open) element.close()
    return () => { if (element.open) element.close() }
  }, [open])

  // Native dialog: Escape, focus trap and return focus. The inner panel fills it, so a click on the dialog itself
  // is a click on the dimmed backdrop.
  return <dialog ref={dialog} aria-labelledby={titleId}
    className="fixed inset-0 m-auto h-fit w-[min(470px,calc(100vw-32px))] rounded-[22px] border-0 bg-white p-0 font-sans text-ink-900 shadow-[0_12px_40px_rgb(20_33_61/22%)] backdrop:bg-[rgb(20_33_61/45%)]"
    onCancel={(event) => { event.preventDefault(); onClose() }}
    onClick={(event) => { if (event.target === dialog.current) onClose() }}>
    {open && <div className="px-11 pt-12 pb-11 max-[480px]:px-6 max-[480px]:pt-9 max-[480px]:pb-8">
      <h2 id={titleId} className="m-0 text-center text-[22px] leading-snug font-bold max-[480px]:text-xl">Bạn đã có tài khoản chưa?</h2>
      <div className="mt-10 grid grid-cols-2 gap-5 max-[480px]:mt-8 max-[480px]:gap-3">
        <Link to={REGISTER_PATH + query} onClick={onClose} className={ACTION + ' border border-brand-500 bg-white text-brand-500 hover:bg-brand-50'}>Đăng ký</Link>
        <Link ref={login} to={LOGIN_PATH + query} onClick={onClose} className={ACTION + ' bg-brand-500 text-white hover:bg-brand-600'}>Đăng nhập</Link>
      </div>
    </div>}
  </dialog>
}
