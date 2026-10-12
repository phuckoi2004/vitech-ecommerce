import { useEffect, useState } from 'react'
import { loginCustomer } from '../../lib/auth-api.js'
import { Field, PasswordInput } from '../components/AuthFields.jsx'
import CustomerAuthLayout from '../layouts/CustomerAuthLayout.jsx'
import { FORGOT_PASSWORD_PATH, HOME_PATH, REGISTER_PATH } from '../routes/paths.js'

function Required({ children }) {
  return <>{children} <span className="cauth-required" aria-hidden="true">*</span></>
}

// Customer sign-in (B3.3) with email or phone number; there is no username.
export default function LoginPage() {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // Arrived here from the account page right after changing the password.
  const [passwordChanged] = useState(() => new URLSearchParams(window.location.search).has('doi-mat-khau'))

  useEffect(() => {
    document.title = 'Đăng nhập | VieTech'
  }, [])

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!identifier.trim()) return setError('Vui lòng nhập email hoặc số điện thoại.')
    if (!password) return setError('Vui lòng nhập mật khẩu.')
    setBusy(true)
    try {
      await loginCustomer(identifier, password)
      // The session lives in the refresh cookie; the home page restores it.
      window.location.assign(HOME_PATH)
    } catch (failure) {
      setError(failure.message)
      setBusy(false)
    }
  }

  return <CustomerAuthLayout>
    <h2>Đăng nhập</h2>
    {passwordChanged && !error && <p className="cauth-success" role="status">Đã đổi mật khẩu thành công. Vui lòng đăng nhập lại bằng mật khẩu mới.</p>}
    {error && <p className="cauth-error" role="alert">{error}</p>}
    <form className="cauth-form" onSubmit={submit} noValidate>
      <Field id="login-identifier" label={<Required>Email / Số điện thoại</Required>}>
        <input id="login-identifier" className="cauth-input" placeholder="Nhập email hoặc số điện thoại" autoComplete="username" maxLength={255}
          value={identifier} onChange={(event) => setIdentifier(event.target.value)} disabled={busy} required />
      </Field>
      <PasswordInput id="login-password" label={<Required>Mật khẩu</Required>} placeholder="Nhập mật khẩu" autoComplete="current-password"
        value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} required />
      <div className="cauth-row">
        <a className="cauth-link cauth-small" href={FORGOT_PASSWORD_PATH}>Quên mật khẩu?</a>
      </div>
      <button type="submit" className="cauth-submit" disabled={busy}>{busy && <span className="spinner" />}Đăng nhập</button>
    </form>
    <p className="cauth-footer">Chưa có tài khoản? <a className="cauth-link" href={REGISTER_PATH}>Đăng ký ngay</a></p>
  </CustomerAuthLayout>
}
