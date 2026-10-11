import { useEffect, useState } from 'react'
import { requestPasswordReset, resendOtp, setNewPassword, verifyPasswordReset } from '../../lib/auth-api.js'
import { passwordRules } from '../../lib/password-rules.js'
import { Field, PasswordInput } from '../components/AuthFields.jsx'
import OtpInput from '../components/OtpInput.jsx'
import CustomerAuthLayout from '../layouts/CustomerAuthLayout.jsx'
import { LOGIN_PATH } from '../routes/paths.js'

function currentTime() {
  return Date.now()
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

function BackToLogin() {
  return <p className="cauth-back"><a className="cauth-link cauth-small" href={LOGIN_PATH}><BackIcon />Quay lại đăng nhập</a></p>
}

// Customer password reset (B3.4): email -> emailed OTP -> new password.
export default function ForgotPasswordPage() {
  const [stage, setStage] = useState('email')
  const [email, setEmail] = useState('')
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
    document.title = 'Quên mật khẩu | VieTech'
  }, [])

  useEffect(() => {
    if (stage !== 'otp' && stage !== 'password') return
    const timer = window.setInterval(() => setNow(currentTime()), 1000)
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
      setNow(currentTime())
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
      setNow(currentTime())
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
      setNow(currentTime())
      setCode('')
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy('')
    }
  }

  if (stage === 'done') {
    return <CustomerAuthLayout>
      <div className="cauth-done" role="status">
        <span className="cauth-done-icon"><CheckIcon /></span>
        <h2>Đặt lại mật khẩu thành công</h2>
        <p className="cauth-lead">Mật khẩu của bạn đã được cập nhật. Vui lòng đăng nhập bằng mật khẩu mới.</p>
        <a className="cauth-submit" href={LOGIN_PATH}>Đăng nhập</a>
      </div>
    </CustomerAuthLayout>
  }

  if (stage === 'password') {
    return <CustomerAuthLayout>
      <h2>Tạo mật khẩu mới</h2>
      <p className="cauth-lead">Đặt mật khẩu mới cho tài khoản <strong>{email.trim()}</strong>.</p>
      {error && <p className="cauth-error" role="alert">{error}</p>}
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
      <BackToLogin />
    </CustomerAuthLayout>
  }

  if (stage === 'otp') {
    return <CustomerAuthLayout>
      <h2>Xác thực OTP</h2>
      <p className="cauth-lead">Nhập mã OTP được gửi đến email <strong>{email.trim()}</strong>.</p>
      {error && <p className="cauth-error" role="alert">{error}</p>}
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
    </CustomerAuthLayout>
  }

  return <CustomerAuthLayout>
    <h2>Quên mật khẩu</h2>
    <p className="cauth-lead">Nhập email đã đăng ký để nhận mã OTP khôi phục mật khẩu.</p>
    {error && <p className="cauth-error" role="alert">{error}</p>}
    <form className="cauth-form" onSubmit={submitEmail} noValidate>
      <Field id="forgot-email" label="Email">
        <input id="forgot-email" className="cauth-input" type="email" placeholder="Nhập email đã đăng ký" autoComplete="email" maxLength={255}
          value={email} onChange={(event) => setEmail(event.target.value)} disabled={!!busy} />
      </Field>
      <p className="cauth-hint">Hệ thống sẽ kiểm tra email và gửi mã OTP nếu tài khoản tồn tại.</p>
      <button type="submit" className="cauth-submit" disabled={!!busy}>{busy === 'submit' && <span className="spinner" />}Gửi mã OTP</button>
    </form>
    <BackToLogin />
  </CustomerAuthLayout>
}
