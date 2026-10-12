import { useEffect, useState } from 'react'
import { createStaff, deleteUser, getUserDefaultAddress, listUsers, updateUser } from '../../lib/admin-users-api.js'
import { passwordRules } from '../../lib/password-rules.js'
import Icon from '../components/Icon.jsx'
import Modal from '../components/Modal.jsx'
import PasswordField, { PasswordRules } from '../components/PasswordField.jsx'
import './AccountsPage.css'

const PAGE_SIZE = 20
const ROLE_LABELS = { Customer: 'Khách hàng', Staff: 'Nhân viên', Admin: 'Quản trị viên' }
const STATUS_OPTIONS = [['Active', 'Hoạt động'], ['Locked', 'Tạm khóa'], ['Deleted', 'Ngừng hoạt động']]
const GENDERS = ['Nam', 'Nữ', 'Khác']
const LOCK_DURATIONS = [['1', '1 ngày'], ['3', '3 ngày'], ['7', '7 ngày'], ['30', '30 ngày'], ['custom', 'Chọn thời điểm']]

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—'
}

function formatAddress(address) {
  if (address === undefined) return 'Đang tải…'
  if (address === 'error') return 'Không tải được địa chỉ'
  if (!address) return '—'
  return [address.DetailAddress, address.Ward, address.Province].filter(Boolean).join(', ')
}

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
}

function formatBirthDate(value) {
  if (!value) return '—'
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

function formatMoney(value) {
  return Number(value || 0).toLocaleString('vi-VN') + ' ₫'
}

function statusOf(user) {
  if (user.IsDeleted) return { key: 'deleted', label: 'Ngừng hoạt động' }
  if (user.AccountStatus === 'Locked') return { key: 'locked', label: 'Tạm khóa' }
  return { key: 'active', label: 'Hoạt động' }
}

function sinceText(loadedAt, now) {
  const seconds = Math.max(0, Math.round((now - loadedAt) / 1000))
  if (seconds < 60) return 'vừa xong'
  const minutes = Math.floor(seconds / 60)
  return minutes < 60 ? `${minutes} phút trước` : `${Math.floor(minutes / 60)} giờ trước`
}

function Notice({ notice, onDismiss }) {
  if (!notice) return null
  const success = notice.type === 'success'
  return <div className={`notice ${success ? 'notice-success' : 'notice-error'} acc-notice`} role={success ? 'status' : 'alert'}>
    <Icon name={success ? 'check' : 'alert'} /><span>{notice.text}</span>
    {onDismiss && <button type="button" className="acc-notice-close" onClick={onDismiss} aria-label="Đóng thông báo">×</button>}
  </div>
}

function Field({ id, label, hint, children, wide = false }) {
  return <div className={`acc-field ${wide ? 'is-wide' : ''}`}>
    <label htmlFor={id}>{label}</label>
    {children}
    {hint && <p className="acc-hint">{hint}</p>}
  </div>
}

function RoleBadge({ role }) {
  return <span className={`acc-badge role-${role.toLowerCase()}`}>{ROLE_LABELS[role] ?? role}</span>
}

function StatusBadge({ user }) {
  const status = statusOf(user)
  return <span className={`acc-badge status-${status.key}`}>{status.label}</span>
}

// ---------------------------------------------------------------------------
// Dialogs
// ---------------------------------------------------------------------------

function DetailDialog({ user, auth, onClose, onDone }) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // undefined while loading; null when the customer has no saved address.
  const [address, setAddress] = useState(undefined)
  const isCustomer = user.Role === 'Customer'
  const { withAccessToken } = auth

  useEffect(() => {
    if (!isCustomer) return
    let active = true
    withAccessToken((token) => getUserDefaultAddress(token, user.UserId))
      .then((saved) => { if (active) setAddress(saved) })
      .catch(() => { if (active) setAddress('error') })
    return () => { active = false }
  }, [withAccessToken, user.UserId, isCustomer])

  async function remove() {
    setBusy(true)
    setError('')
    try {
      await auth.withAccessToken((token) => deleteUser(token, user.UserId))
      onDone(`Đã xóa tài khoản ${user.FullName}.`)
    } catch (failure) {
      setError(failure.message)
      setBusy(false)
    }
  }

  const rows = [
    ['Họ và tên', user.FullName],
    ['Email', user.Email],
    ['Số điện thoại', user.PhoneNumber],
    ['Vai trò', <RoleBadge key="role" role={user.Role} />],
    ['Trạng thái', <StatusBadge key="status" user={user} />],
    ['Giới tính', user.Gender || '—'],
    ['Ngày sinh', formatBirthDate(user.DateOfBirth)],
    ['Ngày tạo', formatDateTime(user.CreatedAt)],
    ['Cập nhật gần nhất', formatDateTime(user.UpdatedAt)],
  ]
  if (isCustomer) rows.push(['Địa chỉ', formatAddress(address)], ['Tổng số đơn', user.TotalOrders], ['Tổng chi tiêu', formatMoney(user.TotalSpent)])
  if (user.AccountStatus === 'Locked' && !user.IsDeleted) rows.push(['Khóa đến', formatDateTime(user.LockedUntil)], ['Lý do khóa', user.LockReason || '—'])

  return <Modal open title="Chi tiết tài khoản" onClose={onClose} busy={busy} wide footer={<>
    {!user.IsDeleted && (confirmDelete
      ? <>
        <span className="acc-confirm-text">Xóa tài khoản này?</span>
        <button type="button" className="acc-button is-danger" onClick={remove} disabled={busy}>{busy && <span className="spinner" />}Xác nhận xóa</button>
        <button type="button" className="acc-button" onClick={() => setConfirmDelete(false)} disabled={busy}>Không</button>
      </>
      : <button type="button" className="acc-button is-danger-outline acc-footer-start" onClick={() => setConfirmDelete(true)}>Xóa tài khoản</button>)}
    {!confirmDelete && <button type="button" className="acc-button is-danger" onClick={onClose}>Đóng</button>}
  </>}>
    {confirmDelete && <p className="acc-warning">Tài khoản sẽ bị đăng xuất khỏi mọi thiết bị và không thể đăng nhập lại. Lịch sử đơn hàng vẫn được giữ.</p>}
    <Notice notice={error && { type: 'error', text: error }} />
    <dl className="acc-detail">
      {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
  </Modal>
}

function profileChanges(form, user) {
  const next = {
    FullName: form.FullName.trim(),
    PhoneNumber: form.PhoneNumber.trim(),
    Gender: form.Gender || null,
    DateOfBirth: form.DateOfBirth || null,
  }
  return Object.fromEntries(Object.entries(next).filter(([key, value]) => value !== (user[key] ?? null)))
}

function EditDialog({ user, auth, onClose, onDone }) {
  const [form, setForm] = useState({
    FullName: user.FullName, PhoneNumber: user.PhoneNumber,
    Gender: user.Gender ?? '', DateOfBirth: user.DateOfBirth ?? '',
  })
  const [today] = useState(() => new Date().toLocaleDateString('en-CA'))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const changes = profileChanges(form, user)
  const genders = form.Gender && !GENDERS.includes(form.Gender) ? [...GENDERS, form.Gender] : GENDERS

  function edit(key) {
    return (event) => setForm({ ...form, [key]: event.target.value })
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!form.FullName.trim()) return setError('Họ và tên không được để trống.')
    if (!form.PhoneNumber.trim()) return setError('Số điện thoại không được để trống.')
    if (form.DateOfBirth && form.DateOfBirth > today) return setError('Ngày sinh không được ở tương lai.')
    setBusy(true)
    try {
      await auth.withAccessToken((token) => updateUser(token, user.UserId, changes))
      onDone(`Đã cập nhật tài khoản ${form.FullName.trim()}.`)
    } catch (failure) {
      setError(failure.message)
      setBusy(false)
    }
  }

  return <Modal open title="Sửa thông tin tài khoản" description={`${ROLE_LABELS[user.Role]} · ${user.Email}`} onClose={onClose} busy={busy} footer={<>
    <button type="button" className="acc-button" onClick={onClose} disabled={busy}>Hủy</button>
    <button type="submit" form="acc-edit-form" className="acc-button is-primary" disabled={busy || !Object.keys(changes).length}>{busy && <span className="spinner" />}Lưu thay đổi</button>
  </>}>
    <Notice notice={error && { type: 'error', text: error }} />
    <form id="acc-edit-form" className="acc-form" onSubmit={submit} noValidate>
      <Field id="edit-name" label="Họ và tên" wide><input id="edit-name" className="acc-input" value={form.FullName} onChange={edit('FullName')} maxLength={255} disabled={busy} /></Field>
      <Field id="edit-phone" label="Số điện thoại"><input id="edit-phone" className="acc-input" type="tel" value={form.PhoneNumber} onChange={edit('PhoneNumber')} maxLength={20} disabled={busy} /></Field>
      <Field id="edit-birth" label="Ngày sinh"><input id="edit-birth" className="acc-input" type="date" max={today} value={form.DateOfBirth} onChange={edit('DateOfBirth')} disabled={busy} /></Field>
      <Field id="edit-gender" label="Giới tính">
        <select id="edit-gender" className="acc-input" value={form.Gender} onChange={edit('Gender')} disabled={busy}>
          <option value="">Chưa chọn</option>
          {genders.map((gender) => <option key={gender} value={gender}>{gender}</option>)}
        </select>
      </Field>
      <p className="acc-hint is-wide">Email và mật khẩu do chính chủ tài khoản thay đổi qua xác minh, không sửa tại đây.</p>
    </form>
  </Modal>
}

function isFuture(date) {
  return Boolean(date) && !Number.isNaN(date.getTime()) && date.getTime() > Date.now()
}

function toLocalInput(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

function LockDialog({ user, auth, onClose, onDone }) {
  const [reason, setReason] = useState('')
  const [duration, setDuration] = useState('7')
  const [opened] = useState(() => Date.now())
  const [custom, setCustom] = useState(() => toLocalInput(new Date(opened + 86400000)))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const until = duration === 'custom' ? (custom ? new Date(custom) : null) : new Date(opened + Number(duration) * 86400000)

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!reason.trim()) return setError('Vui lòng nhập lý do khóa.')
    if (!isFuture(until)) return setError('Thời hạn khóa phải ở tương lai.')
    setBusy(true)
    try {
      await auth.withAccessToken((token) => updateUser(token, user.UserId, {
        AccountStatus: 'Locked', LockReason: reason.trim(), LockedUntil: until.toISOString(),
      }))
      onDone(`Đã khóa tài khoản ${user.FullName} đến ${formatDateTime(until)}.`)
    } catch (failure) {
      setError(failure.message)
      setBusy(false)
    }
  }

  return <Modal open title="Khóa tài khoản" description={`${user.FullName} · ${user.Email}`} onClose={onClose} busy={busy} footer={<>
    <button type="button" className="acc-button" onClick={onClose} disabled={busy}>Hủy</button>
    <button type="submit" form="acc-lock-form" className="acc-button is-warning" disabled={busy}>{busy && <span className="spinner" />}Khóa tài khoản</button>
  </>}>
    <p className="acc-warning">Tài khoản sẽ bị đăng xuất khỏi mọi thiết bị và không đăng nhập được cho đến hết thời hạn khóa. Hết hạn, hệ thống tự mở khóa.</p>
    <Notice notice={error && { type: 'error', text: error }} />
    <form id="acc-lock-form" className="acc-form" onSubmit={submit} noValidate>
      <Field id="lock-reason" label="Lý do khóa" wide>
        <textarea id="lock-reason" className="acc-input acc-textarea" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={2000} rows={3} placeholder="Ví dụ: Vi phạm chính sách mua hàng" disabled={busy} />
      </Field>
      <Field id="lock-duration" label="Thời hạn khóa">
        <select id="lock-duration" className="acc-input" value={duration} onChange={(event) => setDuration(event.target.value)} disabled={busy}>
          {LOCK_DURATIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </Field>
      {duration === 'custom'
        ? <Field id="lock-until" label="Khóa đến"><input id="lock-until" className="acc-input" type="datetime-local" min={toLocalInput(new Date(opened))} value={custom} onChange={(event) => setCustom(event.target.value)} disabled={busy} /></Field>
        : <Field id="lock-until-preview" label="Khóa đến"><input id="lock-until-preview" className="acc-input" value={formatDateTime(until)} readOnly /></Field>}
    </form>
  </Modal>
}

function UnlockDialog({ user, auth, onClose, onDone }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function unlock() {
    setBusy(true)
    setError('')
    try {
      await auth.withAccessToken((token) => updateUser(token, user.UserId, { AccountStatus: 'Active' }))
      onDone(`Đã mở khóa tài khoản ${user.FullName}.`)
    } catch (failure) {
      setError(failure.message)
      setBusy(false)
    }
  }

  return <Modal open title="Mở khóa tài khoản" onClose={onClose} busy={busy} footer={<>
    <button type="button" className="acc-button" onClick={onClose} disabled={busy}>Hủy</button>
    <button type="button" className="acc-button is-success" onClick={unlock} disabled={busy}>{busy && <span className="spinner" />}Mở khóa</button>
  </>}>
    <Notice notice={error && { type: 'error', text: error }} />
    <p className="acc-text">Mở khóa tài khoản <strong>{user.FullName}</strong> ({user.Email}) trước thời hạn?</p>
    <dl className="acc-detail is-compact">
      <div><dt>Khóa đến</dt><dd>{formatDateTime(user.LockedUntil)}</dd></div>
      <div><dt>Lý do khóa</dt><dd>{user.LockReason || '—'}</dd></div>
    </dl>
  </Modal>
}

const EMPTY_STAFF = { Email: '', PhoneNumber: '', FullName: '', Password: '', ConfirmPassword: '', Gender: '', DateOfBirth: '' }

function CreateStaffPage({ auth, onBack, onDone, onDirtyChange }) {
  const [form, setForm] = useState(EMPTY_STAFF)
  const [today] = useState(() => new Date().toLocaleDateString('en-CA'))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const rules = passwordRules(form.Password)
  const dirty = Object.values(form).some((value) => value !== '')

  useEffect(() => { onDirtyChange(dirty) }, [dirty, onDirtyChange])
  useEffect(() => { window.scrollTo(0, 0) }, [])

  function edit(key) {
    return (event) => setForm({ ...form, [key]: event.target.value })
  }

  function back() {
    if (dirty && !window.confirm('Thông tin đã nhập chưa được lưu. Quay lại danh sách?')) return
    onBack()
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    const fail = (message) => { setError(message); window.scrollTo(0, 0) }
    if (!form.FullName.trim()) return fail('Họ và tên không được để trống.')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.Email.trim())) return fail('Vui lòng nhập email hợp lệ.')
    if (!form.PhoneNumber.trim()) return fail('Số điện thoại không được để trống.')
    if (form.DateOfBirth && form.DateOfBirth > today) return fail('Ngày sinh không được ở tương lai.')
    if (!rules.every((rule) => rule.met)) return fail('Mật khẩu chưa đáp ứng đủ yêu cầu.')
    if (form.Password !== form.ConfirmPassword) return fail('Xác nhận mật khẩu không khớp.')
    setBusy(true)
    try {
      const created = await auth.withAccessToken((token) => createStaff(token, {
        Email: form.Email.trim(), PhoneNumber: form.PhoneNumber.trim(), FullName: form.FullName.trim(),
        Password: form.Password, ConfirmPassword: form.ConfirmPassword,
        Gender: form.Gender || null, DateOfBirth: form.DateOfBirth || null,
      }))
      onDone(`Đã tạo tài khoản nhân viên ${created.FullName}. Nhân viên có thể đăng nhập ngay bằng email hoặc số điện thoại và mật khẩu vừa tạo.`)
    } catch (failure) {
      fail(failure.message)
      setBusy(false)
    }
  }

  return <section className="acc-page acc-create" aria-labelledby="acc-create-title">
    <div className="acc-header">
      <div>
        <button type="button" className="acc-back" onClick={back} disabled={busy}><Icon name="back" />Quay lại danh sách</button>
        <h2 id="acc-create-title">Thêm tài khoản nhân viên</h2>
      </div>
    </div>

    <Notice notice={error && { type: 'error', text: error }} />

    <form className="acc-card acc-create-card" onSubmit={submit} noValidate autoComplete="off">
      <h3 className="acc-section-title">Thông tin cá nhân</h3>
      <div className="acc-form">
        <Field id="create-name" label="Họ và tên"><input id="create-name" className="acc-input" value={form.FullName} onChange={edit('FullName')} maxLength={255} disabled={busy} /></Field>
        <Field id="create-role" label="Vai trò"><input id="create-role" className="acc-input" value="Nhân viên" readOnly /></Field>
        <Field id="create-email" label="Email"><input id="create-email" className="acc-input" type="email" value={form.Email} onChange={edit('Email')} maxLength={255} disabled={busy} /></Field>
        <Field id="create-phone" label="Số điện thoại"><input id="create-phone" className="acc-input" type="tel" value={form.PhoneNumber} onChange={edit('PhoneNumber')} maxLength={20} disabled={busy} /></Field>
        <Field id="create-gender" label="Giới tính">
          <select id="create-gender" className="acc-input" value={form.Gender} onChange={edit('Gender')} disabled={busy}>
            <option value="">Chưa chọn</option>
            {GENDERS.map((gender) => <option key={gender} value={gender}>{gender}</option>)}
          </select>
        </Field>
        <Field id="create-birth" label="Ngày sinh"><input id="create-birth" className="acc-input" type="date" max={today} value={form.DateOfBirth} onChange={edit('DateOfBirth')} disabled={busy} /></Field>
      </div>

      <h3 className="acc-section-title">Mật khẩu đăng nhập</h3>
      <div className="acc-password">
        <PasswordField id="create-password" label="Mật khẩu ban đầu" placeholder="Nhập mật khẩu" autoComplete="new-password" value={form.Password} onChange={edit('Password')} disabled={busy} />
        <PasswordField id="create-confirm" label="Xác nhận mật khẩu" placeholder="Nhập lại mật khẩu" autoComplete="new-password" value={form.ConfirmPassword} onChange={edit('ConfirmPassword')} disabled={busy} />
        <PasswordRules rules={rules} />
      </div>

      <div className="acc-create-actions">
        <button type="button" className="acc-button" onClick={back} disabled={busy}>Hủy</button>
        <button type="submit" className="acc-button is-primary" disabled={busy}>{busy && <span className="spinner" />}Tạo tài khoản</button>
      </div>
    </form>
  </section>
}

// ---------------------------------------------------------------------------
// Account list
// ---------------------------------------------------------------------------

function AccountList({ auth, reloadKey, onNotice }) {
  const { withAccessToken } = auth
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [refresh, setRefresh] = useState(0)
  const [result, setResult] = useState(null)
  const [now, setNow] = useState(Date.now)
  const [dialog, setDialog] = useState(null)
  const key = JSON.stringify([debouncedSearch, role, status, page, reloadKey, refresh])
  const loading = result?.key !== key

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 350)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    let active = true
    withAccessToken((token) => listUsers(token, { page, pageSize: PAGE_SIZE, search: debouncedSearch, role, status }))
      .then((data) => {
        if (!active) return
        // A deletion can leave the current page empty; step back to the last page with rows.
        if (!data.Items.length && page > 1) setPage(Math.max(1, Math.ceil(data.Total / PAGE_SIZE)))
        else setResult({ key, data, error: '', at: Date.now() })
      })
      .catch((failure) => { if (active) setResult({ key, data: null, error: failure.message, at: Date.now() }) })
    return () => { active = false }
  }, [withAccessToken, key, debouncedSearch, role, status, page])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30000)
    return () => window.clearInterval(timer)
  }, [])

  const data = result?.data
  const filtered = Boolean(debouncedSearch || role || status)
  const pages = data ? Math.max(1, Math.ceil(data.Total / PAGE_SIZE)) : 1
  const first = data && data.Total ? (data.Page - 1) * PAGE_SIZE + 1 : 0
  const last = data ? first + data.Items.length - Math.min(1, data.Items.length) : 0

  function reset() {
    setSearch('')
    setDebouncedSearch('')
    setRole('')
    setStatus('')
    setPage(1)
  }

  function done(message) {
    setDialog(null)
    onNotice({ type: 'success', text: message })
    setNow(Date.now())
    setRefresh((value) => value + 1)
  }

  const dialogProps = dialog && { user: dialog.user, auth, onClose: () => setDialog(null), onDone: done }

  return <>
    <div className="acc-filters" role="search">
      <div className="acc-search">
        <input className="acc-input" type="search" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Tìm tên, email hoặc số điện thoại…" aria-label="Tìm tài khoản" maxLength={100} />
      </div>
      <select className="acc-input" value={role} onChange={(event) => { setRole(event.target.value); setPage(1) }} aria-label="Lọc theo vai trò">
        <option value="">Tất cả vai trò</option>
        <option value="Staff">Nhân viên</option>
        <option value="Customer">Khách hàng</option>
      </select>
      <select className="acc-input" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }} aria-label="Lọc theo trạng thái">
        <option value="">Tất cả trạng thái</option>
        {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <button type="button" className="acc-button acc-reset" onClick={reset} disabled={!filtered && !search}>Đặt lại</button>
    </div>

    <div className="acc-card">
      <div className="acc-card-head">
        <div className="acc-card-title">
          <h3>Danh sách tài khoản</h3>
          {data && <span className="acc-count">{data.Total.toLocaleString('vi-VN')} tài khoản</span>}
          {loading && result && <span className="spinner acc-inline-spinner" aria-label="Đang tải" />}
        </div>
        {result?.at && <button type="button" className="acc-updated" onClick={() => setRefresh((value) => value + 1)} title="Tải lại danh sách">
          Cập nhật dữ liệu gần nhất: {sinceText(result.at, now)}
        </button>}
      </div>

      {result?.error && !loading
        ? <div className="acc-empty"><Notice notice={{ type: 'error', text: result.error }} /><button type="button" className="acc-button" onClick={() => setRefresh((value) => value + 1)}>Thử lại</button></div>
        : !data
          ? <div className="acc-empty" role="status"><span className="spinner" />Đang tải danh sách…</div>
          : !data.Items.length
            ? <div className="acc-empty">{filtered ? 'Không tìm thấy tài khoản phù hợp với bộ lọc.' : 'Chưa có tài khoản nào.'}</div>
            : <div className={`acc-table-wrap ${loading ? 'is-loading' : ''}`}>
              <table className="acc-table">
                <thead><tr><th>Họ tên</th><th>Email / Số điện thoại</th><th>Vai trò</th><th>Trạng thái</th><th>Ngày tạo</th><th>Thao tác</th></tr></thead>
                <tbody>
                  {data.Items.map((user) => <tr key={user.UserId}>
                    <td className="acc-name">{user.FullName}</td>
                    <td className="acc-contact"><span>{user.Email}</span><span>{user.PhoneNumber}</span></td>
                    <td><RoleBadge role={user.Role} /></td>
                    <td><StatusBadge user={user} /></td>
                    <td className="acc-date">{formatDate(user.CreatedAt)}</td>
                    <td><div className="acc-actions">
                      <button type="button" className="acc-link" onClick={() => setDialog({ type: 'view', user })}>Xem</button>
                      {!user.IsDeleted && <>
                        <button type="button" className="acc-link" onClick={() => setDialog({ type: 'edit', user })}>Sửa</button>
                        {user.AccountStatus === 'Locked'
                          ? <button type="button" className="acc-link is-success" onClick={() => setDialog({ type: 'unlock', user })}>Mở khóa</button>
                          : <button type="button" className="acc-link is-warning" onClick={() => setDialog({ type: 'lock', user })}>Khóa</button>}
                      </>}
                    </div></td>
                  </tr>)}
                </tbody>
              </table>
            </div>}

      {data && data.Total > PAGE_SIZE && <div className="acc-pagination">
        <span>Hiển thị {first}–{last} / {data.Total.toLocaleString('vi-VN')}</span>
        <div>
          <button type="button" className="acc-button" onClick={() => setPage(page - 1)} disabled={page <= 1 || loading}>Trước</button>
          <span className="acc-page-number">Trang {page} / {pages}</span>
          <button type="button" className="acc-button" onClick={() => setPage(page + 1)} disabled={page >= pages || loading}>Sau</button>
        </div>
      </div>}
    </div>

    {dialog?.type === 'view' && <DetailDialog {...dialogProps} />}
    {dialog?.type === 'edit' && <EditDialog {...dialogProps} />}
    {dialog?.type === 'lock' && <LockDialog {...dialogProps} />}
    {dialog?.type === 'unlock' && <UnlockDialog {...dialogProps} />}
  </>
}

export default function AccountsPage({ auth, onSubPage }) {
  const [creating, setCreating] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [notice, setNotice] = useState(null)
  const [unsaved, setUnsaved] = useState(false)

  useEffect(() => {
    if (!unsaved) return
    const warn = (event) => { event.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsaved])

  useEffect(() => {
    onSubPage?.(creating ? 'Thêm tài khoản' : null)
  }, [creating, onSubPage])

  function openCreate() {
    setNotice(null)
    setCreating(true)
  }

  function closeCreate() {
    setUnsaved(false)
    setCreating(false)
  }

  function created(message) {
    closeCreate()
    setNotice({ type: 'success', text: message })
    setReloadKey((value) => value + 1)
  }

  if (creating) return <CreateStaffPage auth={auth} onBack={closeCreate} onDone={created} onDirtyChange={setUnsaved} />

  return <section className="acc-page" aria-label="Quản lý tài khoản">
    <div className="acc-header is-actions-only">
      <button type="button" className="acc-button is-primary acc-add" onClick={openCreate}>+ Thêm tài khoản</button>
    </div>

    <Notice notice={notice} onDismiss={() => setNotice(null)} />
    <AccountList auth={auth} reloadKey={reloadKey} onNotice={setNotice} />
  </section>
}
