import { useEffect, useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { requestPasswordReset, resendOtp, setNewPassword, verifyPasswordReset } from '../../lib/auth-api.js'
import logo from '../../assets/auth/vietech-logo.png'
import Icon from '../components/Icon.jsx'
import PasswordField from '../components/PasswordField.jsx'
import { passwordRules } from '../../lib/password-rules.js'
import { Field, PasswordInput } from '../../customer/components/AuthFields.jsx'
import OtpInput from '../../customer/components/OtpInput.jsx'
import '../../customer/layouts/CustomerAuthLayout.css'
import AdminHomePage from './AdminHomePage.jsx'

const LOGIN_PATH = '/admin/login'
const RESET_PATH = '/admin/forgot-password'
const PAGE_PATHS = { login: LOGIN_PATH, reset: RESET_PATH }
const PAGE_TITLES = { login: 'Đăng nhập nội bộ', reset: 'Quên mật khẩu' }

function pageFromPath(pathname) {
  return Object.keys(PAGE_PATHS).find((page) => PAGE_PATHS[page] === pathname) ?? 'login'
}

function Notice({ children, success = false }) {
  if (!children) return null
  return <div className={`notice ${success ? 'notice-success' : 'notice-error'}`} role={success ? 'status' : 'alert'}><Icon name={success ? 'check' : 'alert'} /><span>{children}</span></div>
}

function TextField({ id, label, icon = 'user', hint, className = '', ...inputProps }) {
  return <div className={`field ${className}`}>
    <label htmlFor={id}>{label}</label>
    <div className="input-wrap"><Icon name={icon} /><input id={id} aria-describedby={hint ? `${id}-hint` : undefined} {...inputProps} /></div>
    {hint && <p className="field-hint" id={`${id}-hint`}>{hint}</p>}
  </div>
}

function SubmitButton({ busy, children, disabled = false }) {
  return <button className="primary-button" type="submit" disabled={disabled || busy} aria-busy={busy}>
    {busy ? <><span className="spinner" />Đang xử lý…</> : <>{children}<Icon name="arrow" /></>}
  </button>
}

function LoginForm({ auth, onForgot, initialIdentifier, successMessage }) {
  const [identifier, setIdentifier] = useState(initialIdentifier)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!identifier.trim() || !password) {
      setError(!identifier.trim() ? 'Vui lòng nhập số điện thoại hoặc email.' : 'Vui lòng nhập mật khẩu.')
      return
    }
    try {
      await auth.signIn(identifier, password)
      setPassword('')
    } catch (failure) {
      setError(failure.message)
    }
  }

  return <>
    <div className="card-symbol"><Icon name="lock" /></div>
    <div className="card-heading"><h2>Đăng nhập hệ thống</h2><p>Dành cho quản trị viên và nhân viên VieTech.</p></div>
    <Notice success>{successMessage}</Notice>
    <Notice>{error || auth.error}</Notice>
    <form onSubmit={submit} className="auth-form" noValidate>
      <TextField id="login-identifier" label="Số điện thoại / Email" placeholder="Nhập số điện thoại hoặc email" autoComplete="username" value={identifier} onChange={(event) => setIdentifier(event.target.value)} required maxLength={255} disabled={auth.loading} />
      <PasswordField id="login-password" placeholder="Nhập mật khẩu" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required disabled={auth.loading} />
      <div className="login-options"><button type="button" className="text-button" onClick={onForgot} disabled={auth.loading}>Quên mật khẩu?</button></div>
      <SubmitButton busy={auth.loading}>Đăng nhập</SubmitButton>
    </form>
  </>
}

function makeChallenge(response) {
  const now = Date.now()
  return { id: response.challenge_id, expiresAt: now + response.expires_in * 1000, resendAt: now + response.resend_after * 1000 }
}

function CheckIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
}

function BackIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 12H5m6-6-6 6 6 6" /></svg>
}

// Same look and steps as the customer reset page (email -> OTP -> new password), inside the internal card.
function ResetForm({ onBack, onComplete, initialIdentifier }) {
  const [stage, setStage] = useState('email')
  const [email, setEmail] = useState(initialIdentifier.includes('@') ? initialIdentifier : '')
  const [code, setCode] = useState('')
  const [challenge, setChallenge] = useState(null)
  const [grant, setGrant] = useState(null)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [now, setNow] = useState(Date.now)
  const rules = passwordRules(password)
  const otpRemaining = Math.max(0, Math.ceil(((challenge?.expiresAt || 0) - now) / 1000))
  const resendRemaining = Math.max(0, Math.ceil(((challenge?.resendAt || 0) - now) / 1000))
  const grantRemaining = Math.max(0, Math.ceil(((grant?.expiresAt || 0) - now) / 1000))

  useEffect(() => {
    if (stage !== 'otp' && stage !== 'password') return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [stage])

  function restart() {
    setStage('email')
    setChallenge(null)
    setGrant(null)
    setCode('')
    setPassword('')
    setConfirmPassword('')
    setError('')
  }

  async function submitEmail(event) {
    event.preventDefault()
    setError('')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return setError('Vui lòng nhập email hợp lệ.')
    setBusy('submit')
    try {
      setChallenge(makeChallenge(await requestPasswordReset(email)))
      setNow(Date.now())
      setCode('')
      setStage('otp')
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy('')
    }
  }

  async function submitCode(event) {
    event.preventDefault()
    setError('')
    if (!/^[0-9]{6}$/.test(code)) return setError('Mã OTP gồm 6 chữ số.')
    if (otpRemaining === 0) return setError('Mã OTP đã hết hạn. Vui lòng gửi lại mã.')
    setBusy('submit')
    try {
      const result = await verifyPasswordReset(challenge.id, code)
      setGrant({ token: result.reset_token, expiresAt: Date.now() + result.expires_in * 1000 })
      setNow(Date.now())
      setStage('password')
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy('')
    }
  }

  async function submitPassword(event) {
    event.preventDefault()
    setError('')
    if (grantRemaining === 0) return setError('Yêu cầu đặt lại mật khẩu đã hết hạn. Vui lòng bắt đầu lại.')
    if (!rules.every((rule) => rule.met)) return setError('Mật khẩu cần ít nhất 8 ký tự, có chữ hoa, chữ số và ký tự đặc biệt.')
    if (password !== confirmPassword) return setError('Xác nhận mật khẩu không khớp.')
    setBusy('submit')
    try {
      await setNewPassword(grant.token, password, confirmPassword)
      setGrant(null)
      setPassword('')
      setConfirmPassword('')
      setStage('done')
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy('')
    }
  }

  async function resend() {
    setBusy('resend')
    setError('')
    try {
      setChallenge(makeChallenge(await resendOtp(challenge.id)))
      setNow(Date.now())
      setCode('')
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy('')
    }
  }

  const errorNotice = error && <p className="cauth-error" role="alert">{error}</p>
  const backToLogin = <p className="cauth-back">
    <button type="button" className="cauth-link cauth-small" onClick={onBack} disabled={!!busy}><BackIcon />Quay lại đăng nhập</button>
  </p>

  if (stage === 'done') {
    return <div className="cauth-panel cauth-done" role="status">
      <span className="cauth-done-icon"><CheckIcon /></span>
      <h2>Đặt lại mật khẩu thành công</h2>
      <p className="cauth-lead">Mật khẩu của bạn đã được cập nhật. Vui lòng đăng nhập bằng mật khẩu mới.</p>
      <button type="button" className="cauth-submit" onClick={() => onComplete(email.trim())}>Đăng nhập</button>
    </div>
  }

  if (stage === 'password') {
    return <div className="cauth-panel">
      <h2>Tạo mật khẩu mới</h2>
      <p className="cauth-lead">Đặt mật khẩu mới cho tài khoản <strong>{email.trim()}</strong>.</p>
      {errorNotice}
      <form className="cauth-form" onSubmit={submitPassword} noValidate>
        <PasswordInput id="reset-password" label="Mật khẩu mới" name="mật khẩu mới" placeholder="Nhập mật khẩu mới" autoComplete="new-password"
          value={password} onChange={(event) => setPassword(event.target.value)} disabled={!!busy} />
        <ul className="cauth-rules" aria-label="Yêu cầu mật khẩu">
          {rules.map((rule) => <li key={rule.label} className={rule.met ? 'is-met' : ''}>{rule.label}</li>)}
        </ul>
        <PasswordInput id="reset-confirm" label="Xác nhận mật khẩu mới" name="xác nhận mật khẩu" placeholder="Nhập lại mật khẩu mới" autoComplete="new-password"
          value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} disabled={!!busy} />
        {grantRemaining === 0 && <p className="cauth-hint is-expired">Yêu cầu đã hết hạn. <button type="button" className="cauth-link" onClick={restart}>Bắt đầu lại</button></p>}
        <button type="submit" className="cauth-submit" disabled={!!busy || grantRemaining === 0}>{busy === 'submit' && <span className="spinner" />}Đặt lại mật khẩu</button>
      </form>
      {backToLogin}
    </div>
  }

  if (stage === 'otp') {
    return <div className="cauth-panel">
      <h2>Xác thực OTP</h2>
      <p className="cauth-lead">Nhập mã OTP được gửi đến email <strong>{email.trim()}</strong>.</p>
      {errorNotice}
      <form className="cauth-form" onSubmit={submitCode} noValidate>
        <div className="cauth-field">
          <span className="cauth-label">Mã xác thực OTP</span>
          <OtpInput value={code} onChange={setCode} disabled={!!busy} label="Mã xác thực OTP" autoFocus />
        </div>
        <p className={`cauth-hint ${otpRemaining === 0 ? 'is-expired' : ''}`}>
          {otpRemaining > 0 ? 'Không nhận được mã? Bạn có thể yêu cầu gửi lại OTP.' : 'Mã OTP đã hết hạn. Vui lòng gửi lại OTP.'}
        </p>
        <button type="submit" className="cauth-submit" disabled={!!busy || !/^[0-9]{6}$/.test(code) || otpRemaining === 0}>
          {busy === 'submit' && <span className="spinner" />}Xác thực OTP
        </button>
        <button type="button" className="cauth-secondary" onClick={resend} disabled={!!busy || resendRemaining > 0}>
          {busy === 'resend' ? 'Đang gửi…' : resendRemaining > 0 ? `Gửi lại OTP sau ${resendRemaining}s` : 'Gửi lại OTP'}
        </button>
      </form>
      <p className="cauth-footer"><button type="button" className="cauth-link" onClick={restart} disabled={!!busy}>Đổi email khác</button></p>
    </div>
  }

  return <div className="cauth-panel">
    <h2>Quên mật khẩu</h2>
    <p className="cauth-lead">Nhập email đã đăng ký để nhận mã OTP khôi phục mật khẩu.</p>
    {errorNotice}
    <form className="cauth-form" onSubmit={submitEmail} noValidate>
      <Field id="reset-email" label="Email">
        <input id="reset-email" className="cauth-input" type="email" placeholder="Nhập email đã đăng ký" autoComplete="email" maxLength={255}
          value={email} onChange={(event) => setEmail(event.target.value)} disabled={!!busy} />
      </Field>
      <p className="cauth-hint">Hệ thống sẽ kiểm tra email và gửi mã OTP nếu tài khoản tồn tại.</p>
      <button type="submit" className="cauth-submit" disabled={!!busy}>{busy === 'submit' && <span className="spinner" />}Gửi mã OTP</button>
    </form>
    {backToLogin}
  </div>
}

function AdminAuthPage() {
  const auth = useInternalAuth()
  const [page, setPage] = useState(() => pageFromPath(window.location.pathname))
  const [initialIdentifier, setInitialIdentifier] = useState('')

  useEffect(() => {
    const pop = () => setPage(pageFromPath(window.location.pathname))
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])

  useEffect(() => {
    if (!auth.sessionReady) return
    const currentPath = window.location.pathname.replace(/\/+$/, '')
    const isSectionPath = currentPath === '/admin' || (currentPath.startsWith('/admin/') && !Object.values(PAGE_PATHS).includes(currentPath))
    const path = auth.user ? (isSectionPath ? currentPath : '/admin') : PAGE_PATHS[page]
    if (window.location.pathname !== path) window.history.replaceState(null, '', path)
    // AdminHomePage owns the title once signed in.
    if (!auth.user) document.title = `${PAGE_TITLES[page]} | VieTech`
  }, [auth.user, auth.sessionReady, page])

  function navigate(next) {
    const path = PAGE_PATHS[next]
    if (window.location.pathname !== path) window.history.pushState(null, '', path)
    setPage(next)
  }

  function resetComplete(identifier) {
    setInitialIdentifier(identifier)
    navigate('login')
  }

  if (auth.sessionReady && auth.user) return <AdminHomePage auth={auth} />

  return <div className="auth-page">
    <main className="auth-layout">
      <div className="showcase">
        <img className="showcase-logo" src={logo} alt="Logo VieTech" width="2172" height="724" />
      </div>
      <section className="auth-card" aria-label={page === 'reset' ? 'Khôi phục mật khẩu' : 'Đăng nhập'}>
        {!auth.sessionReady
          ? <div className="session-loading" role="status"><span className="spinner" /><p>Đang mở không gian làm việc…</p></div>
          : page === 'reset'
            ? <ResetForm onBack={() => navigate('login')} onComplete={resetComplete} initialIdentifier={initialIdentifier} />
            : <LoginForm key={initialIdentifier} auth={auth} initialIdentifier={initialIdentifier} successMessage={auth.notice} onForgot={() => navigate('reset')} />}
      </section>
    </main>
  </div>
}

export default AdminAuthPage
