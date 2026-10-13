import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { ACCOUNT_PATH, LOGIN_PATH, REGISTER_PATH } from '../routes/paths.js'

function UserIcon() {
  return <svg className="shop-account-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9.25" /><circle cx="12" cy="10" r="3" /><path d="M6.6 18.4a6.5 6.5 0 0 1 10.8 0" />
  </svg>
}

// Asked only of guests; a signed-in customer goes straight to their account.
function AccountPrompt({ onClose }) {
  const dialog = useRef(null)

  useEffect(() => {
    dialog.current.showModal()
  }, [])

  return <dialog ref={dialog} className="shop-prompt" aria-labelledby="shop-prompt-title"
    onCancel={(event) => { event.preventDefault(); onClose() }}
    onClick={(event) => { if (event.target === dialog.current) onClose() }}>
    <div className="shop-prompt-inner">
      <h2 id="shop-prompt-title">Bạn đã có tài khoản chưa?</h2>
      <div className="shop-prompt-actions">
        <Link className="shop-prompt-button" to={REGISTER_PATH} onClick={onClose}>Đăng ký</Link>
        <Link className="shop-prompt-button is-primary" to={LOGIN_PATH} onClick={onClose}>Đăng nhập</Link>
      </div>
    </div>
  </dialog>
}

export default function AccountButton() {
  const { ready, user } = useCustomerSession()
  const [asking, setAsking] = useState(false)

  if (!ready) return <span className="shop-account-placeholder" aria-hidden="true" />

  if (user) {
    return <Link className="shop-account" to={ACCOUNT_PATH} title="Tài khoản của bạn">
      <UserIcon />
      <span className="shop-account-text"><strong>Tài khoản</strong><span>{user.FullName}</span></span>
    </Link>
  }

  return <>
    <button type="button" className="shop-login" onClick={() => setAsking(true)} aria-haspopup="dialog">
      Đăng nhập<UserIcon />
    </button>
    {asking && <AccountPrompt onClose={() => setAsking(false)} />}
  </>
}
