import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import userIcon from '../../assets/icons/user-circle.svg'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { ACCOUNT_PATH, LOGIN_PATH, REGISTER_PATH } from '../routes/paths.js'

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

const icon = <img className="shop-action-icon" src={userIcon} alt="" width="24" height="24" />

// Header "Tài khoản" entry: the caption above, then "Đăng nhập" for guests or the customer's name.
export default function AccountButton() {
  const { ready, user } = useCustomerSession()
  const [asking, setAsking] = useState(false)

  if (!ready) return <span className="shop-account-placeholder" aria-hidden="true" />

  if (user) {
    return <Link className="shop-action shop-account" to={ACCOUNT_PATH} title="Tài khoản của bạn">
      <span className="shop-action-text"><strong>Tài khoản</strong><span className="shop-account-name">{user.FullName}</span></span>
      {icon}
    </Link>
  }

  // The caption is hidden from assistive technology so the button is announced by its action, "Đăng nhập".
  return <>
    <button type="button" className="shop-action shop-account" onClick={() => setAsking(true)} aria-haspopup="dialog">
      <span className="shop-action-text"><strong aria-hidden="true">Tài khoản</strong><span>Đăng nhập</span></span>
      {icon}
    </button>
    {asking && <AccountPrompt onClose={() => setAsking(false)} />}
  </>
}
