import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import useCustomerSession from '../../hooks/useCustomerSession.js'
import { AVATAR_MAX_BYTES, AVATAR_TYPES, changePassword, getDefaultAddress, saveDefaultAddress, updateProfile, uploadAvatar } from '../../lib/account-api.js'
import { passwordRules } from '../../lib/password-rules.js'
import { EyeIcon, PasswordInput } from '../components/AuthFields.jsx'
import OrderHistory from '../components/order/OrderHistory.jsx'
import '../layouts/CustomerAuthLayout.css'
import './AccountPage.css'

// The open section is `?section=` (none: profile), so links and the back button reach it.
const SECTIONS = [
  { id: 'profile', label: 'Thông tin cá nhân' },
  { id: 'orders', label: 'Lịch sử mua hàng' },
  { id: 'service', label: 'Tra cứu bảo hành và đổi trả' },
]

const GENDERS = ['Nam', 'Nữ', 'Khác']
const ADDRESS_FIELDS = ['Province', 'Ward', 'DetailAddress']

function formFrom(user, address) {
  return {
    FullName: user.FullName ?? '',
    PhoneNumber: user.PhoneNumber ?? '',
    Gender: user.Gender ?? '',
    DateOfBirth: user.DateOfBirth ?? '',
    Province: address?.Province ?? '',
    Ward: address?.Ward ?? '',
    DetailAddress: address?.DetailAddress ?? '',
  }
}

// Only fields that differ from the saved profile are sent; empty optional fields clear the value.
function profileChanges(form, user) {
  const next = {
    FullName: form.FullName.trim(),
    PhoneNumber: form.PhoneNumber.trim(),
    Gender: form.Gender || null,
    DateOfBirth: form.DateOfBirth || null,
  }
  return Object.fromEntries(Object.entries(next).filter(([key, value]) => value !== (user[key] ?? null)))
}

function addressChange(form, address) {
  const next = Object.fromEntries(ADDRESS_FIELDS.map((key) => [key, form[key].trim()]))
  return ADDRESS_FIELDS.some((key) => next[key] !== (address?.[key] ?? '')) ? next : null
}

// Keeps the first 2 and last 3 digits visible: 0912345678 -> 09*****678.
function maskPhone(phone) {
  if (phone.length <= 5) return phone
  return phone.slice(0, 2) + '*'.repeat(phone.length - 5) + phone.slice(-3)
}

function MaskedPhone({ phone }) {
  const [visible, setVisible] = useState(false)
  return <span className="cacc-phone">
    <span>{visible ? phone : maskPhone(phone)}</span>
    <button type="button" className="cacc-eye" onClick={() => setVisible(!visible)} aria-label={visible ? 'Ẩn số điện thoại' : 'Hiện số điện thoại'} aria-pressed={visible}>
      <EyeIcon hidden={visible} />
    </button>
  </span>
}

function Avatar({ user, className }) {
  return <span className={`cacc-avatar ${className}`}>
    {user.AvatarUrl ? <img src={user.AvatarUrl} alt="" /> : <span aria-hidden="true">{user.FullName.trim().charAt(0).toUpperCase()}</span>}
  </span>
}

function Field({ id, label, children }) {
  return <div className="cacc-field">
    <label className="cacc-field-label" htmlFor={id}>{label}</label>
    {children}
  </div>
}

function ChangePasswordDialog({ session, onClose }) {
  const dialog = useRef(null)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const rules = passwordRules(next)

  useEffect(() => {
    dialog.current.showModal()
  }, [])

  function close() {
    if (!busy) onClose()
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!current) return setError('Vui lòng nhập mật khẩu hiện tại.')
    if (!rules.every((rule) => rule.met)) return setError('Mật khẩu mới cần ít nhất 8 ký tự, có chữ hoa, chữ số và ký tự đặc biệt.')
    if (next !== confirm) return setError('Xác nhận mật khẩu không khớp.')
    if (next === current) return setError('Mật khẩu mới phải khác mật khẩu hiện tại.')
    setBusy(true)
    try {
      await session.withAccessToken((token) => changePassword(token, current, next, confirm))
      // The server revoked every session, including this one; the route guard opens the sign-in page
      // with its "password changed" notice.
      session.endSession()
    } catch (failure) {
      setError(failure.message)
      setBusy(false)
    }
  }

  return <dialog ref={dialog} className="cacc-dialog" aria-labelledby="cacc-password-title"
    onCancel={(event) => { event.preventDefault(); close() }}>
    <form onSubmit={submit} noValidate>
      <h2 id="cacc-password-title">Đổi mật khẩu</h2>
      <p className="cacc-dialog-lead">Sau khi đổi, bạn sẽ được đăng xuất khỏi mọi thiết bị và cần đăng nhập lại.</p>
      {error && <p className="cacc-notice" role="alert">{error}</p>}
      <div className="cacc-dialog-body">
        <PasswordInput id="cacc-current-password" label="Mật khẩu hiện tại" name="mật khẩu hiện tại" placeholder="Nhập mật khẩu hiện tại"
          autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} disabled={busy} />
        <PasswordInput id="cacc-new-password" label="Mật khẩu mới" name="mật khẩu mới" placeholder="Nhập mật khẩu mới"
          autoComplete="new-password" value={next} onChange={(event) => setNext(event.target.value)} disabled={busy} />
        <ul className="cauth-rules" aria-label="Yêu cầu mật khẩu">
          {rules.map((rule) => <li key={rule.label} className={rule.met ? 'is-met' : ''}>{rule.label}</li>)}
        </ul>
        <PasswordInput id="cacc-confirm-password" label="Xác nhận mật khẩu mới" name="xác nhận mật khẩu" placeholder="Nhập lại mật khẩu mới"
          autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} disabled={busy} />
      </div>
      <div className="cacc-actions">
        <button type="submit" className="cacc-button" disabled={busy}>{busy && <span className="spinner" />}Đổi mật khẩu</button>
        <button type="button" className="cacc-button is-outline" onClick={close} disabled={busy}>Hủy</button>
      </div>
    </form>
  </dialog>
}

function ProfileSection({ session }) {
  const { user, withAccessToken, updateUser } = session
  // undefined while the saved address is loading; null when the customer has none.
  const [address, setAddress] = useState(undefined)
  const [form, setForm] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [reload, setReload] = useState(0)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [notice, setNotice] = useState(null)
  const [today] = useState(() => new Date().toLocaleDateString('en-CA'))
  const fileInput = useRef(null)
  const [passwordOpen, setPasswordOpen] = useState(false)

  useEffect(() => {
    let active = true
    withAccessToken(getDefaultAddress)
      .then((saved) => { if (active) setAddress(saved) })
      .catch((failure) => { if (active) setLoadError(failure.message) })
    return () => { active = false }
  }, [withAccessToken, reload])

  if (loadError) return <>
    <p className="cacc-notice" role="alert">{loadError}</p>
    <button type="button" className="cacc-button is-outline" onClick={() => {
      setLoadError('')
      setReload((value) => value + 1)
    }}>Thử lại</button>
  </>

  // Fill the form once the address arrives; later saves reset it from the server copy.
  if (!form && address !== undefined) setForm(formFrom(user, address))
  if (!form) return <div className="cacc-loading" role="status"><span className="spinner" />Đang tải thông tin…</div>

  const changes = profileChanges(form, user)
  const newAddress = addressChange(form, address)
  const dirty = Object.keys(changes).length > 0 || newAddress !== null
  const busy = saving || uploading
  const genders = form.Gender && !GENDERS.includes(form.Gender) ? [...GENDERS, form.Gender] : GENDERS

  function edit(key) {
    return (event) => {
      setForm({ ...form, [key]: event.target.value })
      setNotice(null)
    }
  }

  async function save(event) {
    event.preventDefault()
    setNotice(null)
    if (!form.FullName.trim()) return setNotice({ type: 'error', text: 'Họ và tên không được để trống.' })
    if (!form.PhoneNumber.trim()) return setNotice({ type: 'error', text: 'Số điện thoại không được để trống.' })
    if (form.DateOfBirth && form.DateOfBirth > today) return setNotice({ type: 'error', text: 'Ngày sinh không được ở tương lai.' })
    if (newAddress && ADDRESS_FIELDS.some((key) => !newAddress[key])) {
      return setNotice({ type: 'error', text: 'Địa chỉ cần đủ Tỉnh/Thành phố, Phường/Xã và địa chỉ chi tiết.' })
    }
    setSaving(true)
    let saved = user
    let savedAddress = address
    try {
      if (Object.keys(changes).length) {
        saved = await withAccessToken((token) => updateProfile(token, changes))
        updateUser(saved)
      }
      if (newAddress) {
        savedAddress = await withAccessToken((token) => saveDefaultAddress(token, newAddress))
        setAddress(savedAddress)
      }
      setForm(formFrom(saved, savedAddress))
      setNotice({ type: 'success', text: 'Đã cập nhật thông tin.' })
    } catch (failure) {
      // Keep what the customer typed; whatever was already saved is reflected above.
      setNotice({ type: 'error', text: failure.message })
    } finally {
      setSaving(false)
    }
  }

  async function pickAvatar(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setNotice(null)
    if (!AVATAR_TYPES.includes(file.type)) return setNotice({ type: 'error', text: 'Ảnh đại diện phải là tệp JPG, PNG hoặc WEBP.' })
    if (file.size > AVATAR_MAX_BYTES) return setNotice({ type: 'error', text: 'Ảnh đại diện tối đa 2 MB.' })
    setUploading(true)
    try {
      updateUser(await withAccessToken((token) => uploadAvatar(token, file)))
      setNotice({ type: 'success', text: 'Đã cập nhật ảnh đại diện.' })
    } catch (failure) {
      setNotice({ type: 'error', text: failure.message })
    } finally {
      setUploading(false)
    }
  }

  // The dialog stays outside this form: a nested form's submit would also bubble into save().
  return <>
    <form onSubmit={save} noValidate>
      <div className="cacc-panel-heading">
        <h1>Thông tin cá nhân</h1>
        <p>Thông tin tài khoản khách hàng</p>
      </div>
      {notice && <p className={`cacc-notice ${notice.type === 'success' ? 'is-success' : ''}`} role={notice.type === 'success' ? 'status' : 'alert'}>{notice.text}</p>}
      <div className="cacc-profile">
        <div className="cacc-photo">
          <span className="cacc-photo-frame">
            <Avatar user={user} className="is-large" />
            {uploading && <span className="cacc-photo-busy" role="status" aria-label="Đang tải ảnh lên"><span className="spinner" /></span>}
          </span>
          <input ref={fileInput} type="file" accept={AVATAR_TYPES.join(',')} hidden onChange={pickAvatar} />
          <button type="button" className="cacc-button is-outline is-small" onClick={() => fileInput.current.click()} disabled={busy}>Thay ảnh</button>
        </div>
        <div className="cacc-fields">
          <Field id="cacc-name" label="Họ và tên">
            <input id="cacc-name" className="cacc-input" autoComplete="name" maxLength={255} value={form.FullName} onChange={edit('FullName')} disabled={busy} />
          </Field>
          <Field id="cacc-email" label="Email">
            <input id="cacc-email" className="cacc-input" type="email" value={user.Email} readOnly />
          </Field>
          <Field id="cacc-phone" label="Số điện thoại">
            <input id="cacc-phone" className="cacc-input" type="tel" inputMode="tel" autoComplete="tel" maxLength={20} value={form.PhoneNumber} onChange={edit('PhoneNumber')} disabled={busy} />
          </Field>
          <Field id="cacc-birth" label="Ngày sinh">
            <input id="cacc-birth" className="cacc-input" type="date" max={today} value={form.DateOfBirth} onChange={edit('DateOfBirth')} disabled={busy} />
          </Field>
          <Field id="cacc-gender" label="Giới tính">
            <select id="cacc-gender" className="cacc-input" value={form.Gender} onChange={edit('Gender')} disabled={busy}>
              <option value="">Chưa chọn</option>
              {genders.map((gender) => <option key={gender} value={gender}>{gender}</option>)}
            </select>
          </Field>
          <Field id="cacc-province" label="Tỉnh/Thành phố">
            <input id="cacc-province" className="cacc-input" autoComplete="address-level1" maxLength={100} placeholder="VD: Hà Nội" value={form.Province} onChange={edit('Province')} disabled={busy} />
          </Field>
          <Field id="cacc-ward" label="Phường/Xã">
            <input id="cacc-ward" className="cacc-input" autoComplete="address-level3" maxLength={100} placeholder="VD: Phường Cầu Giấy" value={form.Ward} onChange={edit('Ward')} disabled={busy} />
          </Field>
          <Field id="cacc-detail" label="Địa chỉ chi tiết">
            <input id="cacc-detail" className="cacc-input" autoComplete="street-address" maxLength={255} placeholder="Số nhà, tên đường" value={form.DetailAddress} onChange={edit('DetailAddress')} disabled={busy} />
          </Field>
        </div>
      </div>
      <div className="cacc-actions">
        <button type="submit" className="cacc-button" disabled={busy || !dirty}>{saving && <span className="spinner" />}Cập nhật thông tin</button>
        <button type="button" className="cacc-button is-outline" onClick={() => setPasswordOpen(true)} disabled={busy}>Đổi mật khẩu</button>
      </div>
    </form>
    {passwordOpen && <ChangePasswordDialog session={session} onClose={() => setPasswordOpen(false)} />}
  </>
}

// Customer account page (/tai-khoan), inside CustomerLayout behind RequireCustomer, which also handles the
// redirects once the session ends (sign-out: home; password change: sign-in page).
export default function AccountPage() {
  const session = useCustomerSession()
  const { user, signOut } = session
  const [params, setParams] = useSearchParams()
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    document.title = 'Tài khoản | VieTech'
  }, [])

  if (!user) return <div className="cacc-loading" role="status"><span className="spinner" />Đang tải thông tin tài khoản…</div>

  async function logout() {
    setSigningOut(true)
    // Signed out locally even when the server is unreachable; the refresh cookie no longer applies.
    await signOut().catch(() => {})
  }

  const current = SECTIONS.find((item) => item.id === params.get('section')) ?? SECTIONS[0]
  return <>
    <div className="shop-container cacc-page">
      <section className="cacc-card cacc-summary" aria-label="Tóm tắt tài khoản">
        <Avatar user={user} className="is-medium" />
        <div className="cacc-summary-text">
          <strong>{user.FullName}</strong>
          <MaskedPhone phone={user.PhoneNumber} />
        </div>
      </section>
      <div className="cacc-body">
        <nav className="cacc-card cacc-menu" aria-label="Mục tài khoản">
          {SECTIONS.map((item) => <button key={item.id} type="button" className={`cacc-menu-item ${item === current ? 'is-active' : ''}`}
            aria-current={item === current ? 'page' : undefined}
            onClick={() => setParams(item === SECTIONS[0] ? {} : { section: item.id })}>{item.label}</button>)}
          <button type="button" className="cacc-menu-item is-logout" onClick={logout} disabled={signingOut}>
            {signingOut ? 'Đang đăng xuất…' : 'Đăng xuất'}
          </button>
        </nav>
        <section className="cacc-card cacc-panel">
          {current.id === 'profile'
            ? <ProfileSection session={session} />
            : current.id === 'orders'
              ? <OrderHistory />
              : <>
                <div className="cacc-panel-heading"><h1>{current.label}</h1></div>
                <p className="cacc-placeholder">Chức năng đang được xây dựng.</p>
              </>}
        </section>
      </div>
    </div>
  </>
}
