import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { safeNext } from '../../auth/session.js'
import useAuth from '../../auth/useAuth.js'
import { Field, PasswordInput } from '../components/AuthFields.jsx'
import CustomerAuthLayout from '../layouts/CustomerAuthLayout.jsx'
import { FORGOT_PASSWORD_PATH, HOME_PATH, REGISTER_PATH } from '../routes/paths.js'

function Required({ children }) {
  return <>{children} <span className="cauth-required" aria-hidden="true">*</span></>
}

// Customer sign-in (B3.3) with email or phone number; there is no username.
export default function LoginPage() {
  const { signInCustomer } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // Arrived here from the account page right after changing the password.
  const [passwordChanged] = useState(() => searchParams.has('doi-mat-khau'))

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
      await signInCustomer(identifier, password)
      // Back to the page that asked for sign-in (same-site customer pages only), otherwise home.
      navigate(safeNext(searchParams.get('next'), 'customer') ?? HOME_PATH, { replace: true })
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
        <Link className="cauth-link cauth-small" to={FORGOT_PASSWORD_PATH}>Quên mật khẩu?</Link>
      </div>
      <button type="submit" className="cauth-submit" disabled={busy}>{busy && <span className="spinner" />}Đăng nhập</button>
    </form>
    <p className="cauth-footer">Chưa có tài khoản? <Link className="cauth-link" to={REGISTER_PATH}>Đăng ký ngay</Link></p>
  </CustomerAuthLayout>
}
