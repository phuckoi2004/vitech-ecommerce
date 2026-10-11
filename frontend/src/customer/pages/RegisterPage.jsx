import { useEffect, useState } from 'react'
import { registerCustomer, resendOtp, verifyRegistration } from '../../lib/auth-api.js'
import { passwordRules } from '../../lib/password-rules.js'
import { Field, PasswordInput } from '../components/AuthFields.jsx'
import OtpInput from '../components/OtpInput.jsx'
import CustomerAuthLayout from '../layouts/CustomerAuthLayout.jsx'
import { HOME_PATH, LOGIN_PATH } from '../routes/paths.js'

const EMPTY = { FullName: '', Email: '', PhoneNumber: '', Password: '', ConfirmPassword: '' }

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

// Customer sign-up (B3.2): details -> emailed OTP -> account created as Customer.
export default function RegisterPage() {
  const [stage, setStage] = useState('details')
  const [form, setForm] = useState(EMPTY)
  const [code, setCode] = useState('')
  const [challenge, setChallenge] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [now, setNow] = useState(Date.now)
  const rules = passwordRules(form.Password)
  const otpRemaining = Math.max(0, Math.ceil(((challenge?.expiresAt || 0) - now) / 1000))
  const resendRemaining = Math.max(0, Math.ceil(((challenge?.resendAt || 0) - now) / 1000))

  useEffect(() => {
    document.title = 'Đăng ký tài khoản | VieTech'
  }, [])

  useEffect(() => {
    if (stage !== 'otp') return
    const timer = window.setInterval(() => setNow(currentTime()), 1000)
    return () => window.clearInterval(timer)
  }, [stage])

  function edit(key) {
    return (event) => setForm({ ...form, [key]: event.target.value })
  }

  async function submitDetails(event) {
    event.preventDefault()
    setError('')
    if (!form.FullName.trim()) return setError('Vui lòng nhập họ và tên.')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.Email.trim())) return setError('Vui lòng nhập email hợp lệ.')
    if (!form.PhoneNumber.trim()) return setError('Vui lòng nhập số điện thoại.')
    if (!rules.every((rule) => rule.met)) return setError('Mật khẩu cần ít nhất 8 ký tự, có chữ hoa, chữ số và ký tự đặc biệt.')
    if (form.Password !== form.ConfirmPassword) return setError('Xác nhận mật khẩu không khớp.')
    setBusy('submit')
    try {
      setChallenge(makeChallenge(await registerCustomer(form)))
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
      await verifyRegistration(challenge.id, code)
      setForm(EMPTY)
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
        <h2>Đăng ký thành công</h2>
        <p className="cauth-lead">Tài khoản của bạn đã được tạo. Bạn có thể đăng nhập để bắt đầu mua sắm.</p>
        <a className="cauth-submit" href={LOGIN_PATH}>Đăng nhập</a>
        <p className="cauth-footer"><a className="cauth-link" href={HOME_PATH}>Về trang chủ</a></p>
      </div>
    </CustomerAuthLayout>
  }

  if (stage === 'otp') {
    return <CustomerAuthLayout>
      <h2>Xác thực tài khoản</h2>
      <p className="cauth-lead">Nhập mã OTP được gửi đến email <strong>{form.Email.trim()}</strong>.</p>
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
          {busy === 'submit' && <span className="spinner" />}Xác thực và hoàn tất đăng ký
        </button>
        <button type="button" className="cauth-secondary" onClick={resend} disabled={!!busy || resendRemaining > 0}>
          {busy === 'resend' ? 'Đang gửi…' : resendRemaining > 0 ? `Gửi lại OTP sau ${resendRemaining}s` : 'Gửi lại OTP'}
        </button>
      </form>
      <p className="cauth-footer"><button type="button" className="cauth-link" onClick={() => { setError(''); setStage('details') }} disabled={!!busy}>Quay lại trang đăng ký</button></p>
    </CustomerAuthLayout>
  }

  return <CustomerAuthLayout>
    <h2>Đăng ký tài khoản</h2>
    {error && <p className="cauth-error" role="alert">{error}</p>}
    <form className="cauth-form" onSubmit={submitDetails} noValidate>
      <Field id="register-name" label="Họ và tên">
        <input id="register-name" className="cauth-input" placeholder="Nhập họ và tên" autoComplete="name" maxLength={255} value={form.FullName} onChange={edit('FullName')} disabled={!!busy} />
      </Field>
      <Field id="register-email" label="Email">
        <input id="register-email" className="cauth-input" type="email" placeholder="Nhập địa chỉ email" autoComplete="email" maxLength={255} value={form.Email} onChange={edit('Email')} disabled={!!busy} />
      </Field>
      <Field id="register-phone" label="Số điện thoại">
        <input id="register-phone" className="cauth-input" type="tel" inputMode="tel" placeholder="Nhập số điện thoại" autoComplete="tel" maxLength={20} value={form.PhoneNumber} onChange={edit('PhoneNumber')} disabled={!!busy} />
      </Field>
      <PasswordInput id="register-password" label="Mật khẩu" placeholder="Nhập mật khẩu" autoComplete="new-password" value={form.Password} onChange={edit('Password')} disabled={!!busy} />
      <ul className="cauth-rules" aria-label="Yêu cầu mật khẩu">
        {rules.map((rule) => <li key={rule.label} className={rule.met ? 'is-met' : ''}>{rule.label}</li>)}
      </ul>
      <PasswordInput id="register-confirm" label="Xác nhận mật khẩu" name="xác nhận mật khẩu" placeholder="Nhập lại mật khẩu" autoComplete="new-password" value={form.ConfirmPassword} onChange={edit('ConfirmPassword')} disabled={!!busy} />
      <button type="submit" className="cauth-submit" disabled={!!busy}>{busy === 'submit' && <span className="spinner" />}Đăng ký</button>
    </form>
    <p className="cauth-footer">Đã có tài khoản? <a className="cauth-link" href={LOGIN_PATH}>Đăng nhập</a></p>
  </CustomerAuthLayout>
}
