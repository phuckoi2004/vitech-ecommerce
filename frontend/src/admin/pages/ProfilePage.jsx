import { useEffect, useRef, useState } from 'react'
import {
  AVATAR_MAX_BYTES, AVATAR_TYPES, changePassword, getDefaultAddress, getProfile,
  saveDefaultAddress, updateProfile, uploadAvatar,
} from '../../lib/account-api.js'
import Icon from '../components/Icon.jsx'
import PasswordField, { PasswordRules } from '../components/PasswordField.jsx'
import { passwordRules } from '../../lib/password-rules.js'
import { Avatar } from '../layouts/AdminLayout.jsx'
import './ProfilePage.css'

const GENDERS = ['Nam', 'Nữ', 'Khác']
const ADDRESS_FIELDS = ['Province', 'Ward', 'DetailAddress']

function formFrom(profile, address) {
  return {
    FullName: profile.FullName ?? '',
    PhoneNumber: profile.PhoneNumber ?? '',
    Gender: profile.Gender ?? '',
    DateOfBirth: profile.DateOfBirth ?? '',
    Province: address?.Province ?? '',
    Ward: address?.Ward ?? '',
    DetailAddress: address?.DetailAddress ?? '',
  }
}

// Only fields that differ from the server copy are sent; empty optional fields clear the value.
function profileChanges(form, profile) {
  const next = {
    FullName: form.FullName.trim(),
    PhoneNumber: form.PhoneNumber.trim(),
    Gender: form.Gender || null,
    DateOfBirth: form.DateOfBirth || null,
  }
  return Object.fromEntries(Object.entries(next).filter(([key, value]) => value !== (profile[key] ?? null)))
}

function addressChange(form, address) {
  const next = Object.fromEntries(ADDRESS_FIELDS.map((key) => [key, form[key].trim()]))
  return ADDRESS_FIELDS.some((key) => next[key] !== (address?.[key] ?? '')) ? next : null
}

function Notice({ notice }) {
  if (!notice) return null
  const success = notice.type === 'success'
  return <div className={`notice ${success ? 'notice-success' : 'notice-error'}`} role={success ? 'status' : 'alert'}><Icon name={success ? 'check' : 'alert'} /><span>{notice.text}</span></div>
}

function Field({ id, label, hint, children }) {
  return <div className="profile-field">
    <label htmlFor={id}>{label}</label>
    {children}
    {hint && <p className="profile-hint" id={`${id}-hint`}>{hint}</p>}
  </div>
}

function ChangePasswordDialog({ open, onClose, auth }) {
  const dialog = useRef(null)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const rules = passwordRules(next)

  useEffect(() => {
    const element = dialog.current
    if (open && !element.open) element.showModal()
    if (!open && element.open) element.close()
  }, [open])

  function close() {
    if (busy) return
    setCurrent('')
    setNext('')
    setConfirm('')
    setError('')
    onClose()
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!current) return setError('Vui lòng nhập mật khẩu hiện tại.')
    if (!rules.every((rule) => rule.met)) return setError('Mật khẩu mới chưa đáp ứng đủ yêu cầu.')
    if (next !== confirm) return setError('Xác nhận mật khẩu không khớp.')
    if (next === current) return setError('Mật khẩu mới phải khác mật khẩu hiện tại.')
    setBusy(true)
    try {
      await auth.withAccessToken((token) => changePassword(token, current, next, confirm))
      // The server revoked every session, including this one.
      auth.endSession('Đã đổi mật khẩu thành công. Vui lòng đăng nhập lại bằng mật khẩu mới.')
    } catch (failure) {
      setError(failure.message)
      setBusy(false)
    }
  }

  return <dialog ref={dialog} className="profile-dialog" aria-labelledby="change-password-title" onCancel={(event) => { event.preventDefault(); close() }}>
    <form onSubmit={submit} noValidate>
      <div className="profile-dialog-head">
        <h2 id="change-password-title">Đổi mật khẩu</h2>
        <p>Sau khi đổi, bạn sẽ được đăng xuất khỏi mọi thiết bị và cần đăng nhập lại.</p>
      </div>
      <Notice notice={error && { type: 'error', text: error }} />
      <div className="profile-dialog-body">
        <PasswordField id="current-password" label="Mật khẩu hiện tại" placeholder="Nhập mật khẩu hiện tại" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} disabled={busy} />
        <PasswordField id="new-password" label="Mật khẩu mới" placeholder="Nhập mật khẩu mới" autoComplete="new-password" value={next} onChange={(event) => setNext(event.target.value)} disabled={busy} />
        <PasswordRules rules={rules} />
        <PasswordField id="confirm-password" label="Xác nhận mật khẩu mới" placeholder="Nhập lại mật khẩu mới" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} disabled={busy} />
      </div>
      <div className="profile-actions">
        <button type="submit" className="profile-button is-primary" disabled={busy}>{busy && <span className="spinner" />}Đổi mật khẩu</button>
        <button type="button" className="profile-button" onClick={close} disabled={busy}>Hủy</button>
      </div>
    </form>
  </dialog>
}

export default function ProfilePage({ auth }) {
  const { withAccessToken, updateUser } = auth
  const [profile, setProfile] = useState(null)
  const [address, setAddress] = useState(null)
  const [form, setForm] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [reload, setReload] = useState(0)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [notice, setNotice] = useState(null)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const fileInput = useRef(null)
  const [today] = useState(() => new Date().toLocaleDateString('en-CA'))

  useEffect(() => {
    let active = true
    Promise.all([withAccessToken(getProfile), withAccessToken(getDefaultAddress)]).then(([user, saved]) => {
      if (!active) return
      setProfile(user)
      setAddress(saved)
      setForm(formFrom(user, saved))
      updateUser(user)
    }).catch((failure) => {
      if (active) setLoadError(failure.message)
    })
    return () => { active = false }
  }, [withAccessToken, updateUser, reload])

  if (loadError) {
    return <section className="profile-page"><Notice notice={{ type: 'error', text: loadError }} />
      <button type="button" className="profile-button profile-retry" onClick={() => { setLoadError(''); setReload((value) => value + 1) }}>Thử lại</button></section>
  }
  if (!form) return <div className="profile-loading" role="status"><span className="spinner" />Đang tải thông tin…</div>

  const changes = profileChanges(form, profile)
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
    let user = profile
    let saved = address
    try {
      if (Object.keys(changes).length) {
        user = await withAccessToken((token) => updateProfile(token, changes))
        setProfile(user)
        updateUser(user)
      }
      if (newAddress) {
        saved = await withAccessToken((token) => saveDefaultAddress(token, newAddress))
        setAddress(saved)
      }
      setForm(formFrom(user, saved))
      setNotice({ type: 'success', text: 'Đã lưu thay đổi.' })
    } catch (failure) {
      // Keep what the user typed; whatever was already saved is reflected in profile/address.
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
      const user = await withAccessToken((token) => uploadAvatar(token, file))
      setProfile(user)
      updateUser(user)
      setNotice({ type: 'success', text: 'Đã cập nhật ảnh đại diện.' })
    } catch (failure) {
      setNotice({ type: 'error', text: failure.message })
    } finally {
      setUploading(false)
    }
  }

  return <section className="profile-page" aria-label="Thông tin cá nhân">

    <form className="profile-card" onSubmit={save} noValidate>
      <div className="profile-layout">
        <div className="profile-avatar-panel">
          <div className="profile-avatar-frame">
            <Avatar user={profile} className="profile-avatar" />
            {uploading && <span className="profile-avatar-busy" role="status" aria-label="Đang tải ảnh lên"><span className="spinner" /></span>}
          </div>
          <input ref={fileInput} type="file" accept={AVATAR_TYPES.join(',')} hidden onChange={pickAvatar} />
          <button type="button" className="profile-button" onClick={() => fileInput.current.click()} disabled={busy}>Thay ảnh</button>
        </div>

        <div className="profile-grid">
          <Field id="profile-name" label="Họ và tên">
            <input id="profile-name" className="profile-input" value={form.FullName} onChange={edit('FullName')} maxLength={255} autoComplete="name" disabled={busy} />
          </Field>
          <Field id="profile-email" label="Email">
            <input id="profile-email" className="profile-input" value={profile.Email} readOnly />
          </Field>
          <Field id="profile-phone" label="Số điện thoại">
            <input id="profile-phone" className="profile-input" type="tel" inputMode="tel" value={form.PhoneNumber} onChange={edit('PhoneNumber')} maxLength={20} autoComplete="tel" disabled={busy} />
          </Field>
          <Field id="profile-birth" label="Ngày sinh">
            <input id="profile-birth" className="profile-input" type="date" value={form.DateOfBirth} max={today} onChange={edit('DateOfBirth')} disabled={busy} />
          </Field>
          <Field id="profile-gender" label="Giới tính">
            <select id="profile-gender" className="profile-input" value={form.Gender} onChange={edit('Gender')} disabled={busy}>
              <option value="">Chưa chọn</option>
              {genders.map((gender) => <option key={gender} value={gender}>{gender}</option>)}
            </select>
          </Field>

          <fieldset className="profile-address">
            <legend>Địa chỉ</legend>
            <Field id="profile-province" label="Tỉnh/Thành phố">
              <input id="profile-province" className="profile-input" value={form.Province} onChange={edit('Province')} maxLength={100} placeholder="Hà Nội" disabled={busy} />
            </Field>
            <Field id="profile-ward" label="Phường/Xã">
              <input id="profile-ward" className="profile-input" value={form.Ward} onChange={edit('Ward')} maxLength={100} placeholder="Phường Hoàn Kiếm" disabled={busy} />
            </Field>
            <Field id="profile-detail" label="Địa chỉ chi tiết">
              <input id="profile-detail" className="profile-input" value={form.DetailAddress} onChange={edit('DetailAddress')} maxLength={255} placeholder="Số nhà, tên đường" autoComplete="street-address" disabled={busy} />
            </Field>
          </fieldset>
        </div>
      </div>

      <Notice notice={notice} />
      <div className="profile-actions">
        <button type="submit" className="profile-button is-primary" disabled={busy || !dirty}>{saving && <span className="spinner" />}Lưu thay đổi</button>
        <button type="button" className="profile-button" onClick={() => setPasswordOpen(true)} disabled={busy}>Đổi mật khẩu</button>
      </div>
    </form>

    <ChangePasswordDialog open={passwordOpen} onClose={() => setPasswordOpen(false)} auth={auth} />
  </section>
}
