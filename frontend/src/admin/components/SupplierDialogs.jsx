import { useEffect, useRef, useState } from 'react'
import Field from '../../components/shared/Field.jsx'
import { ErrorState, LoadingState } from '../../components/shared/index.js'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import useAdminQuery from '../hooks/useAdminQuery.js'
import { supplierBody } from '../lib/suppliers.js'
import { createSupplier, hideSupplier, updateSupplier } from '../services/suppliers.js'
import Modal from './Modal.jsx'
import { PRODUCT_CONTROL } from './ProductUi.jsx'
import { SupplierButton, SupplierStatus } from './SupplierUi.jsx'

function SupplierError({ message }) {
  return message ? <p role="alert" className="mb-4 rounded-[10px] bg-red-50 p-3 text-xs text-red-700">{message}</p> : null
}

function SupplierEditor({ supplier, onBusy, onClose, onDone }) {
  const auth = useInternalAuth()
  const [form, setForm] = useState(() => ({ SupplierCode: supplier?.SupplierCode ?? '', Name: supplier?.Name ?? '', Email: supplier?.Email ?? '', PhoneNumber: supplier?.PhoneNumber ?? '', Address: supplier?.Address ?? '', TaxCode: supplier?.TaxCode ?? '', Note: supplier?.Note ?? '', IsActive: supplier?.IsActive ?? true }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const writing = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  function change(key, value) { setForm((previous) => ({ ...previous, [key]: value })); setError('') }
  async function save(event) {
    event.preventDefault()
    if (writing.current || !auth.permissions.includes(supplier ? 'suppliers:update' : 'suppliers:create')) return
    let body
    try { body = supplierBody(form) } catch (failure) { setError(failure.message); return }
    writing.current = true; setBusy(true); onBusy(true); setError('')
    try {
      await auth.withAccessToken((token) => supplier ? updateSupplier(token, supplier.SupplierId, body) : createSupplier(token, body))
      if (mounted.current) onDone(supplier ? 'Đã cập nhật nhà cung cấp.' : 'Đã thêm nhà cung cấp.')
    } catch (failure) { if (mounted.current) setError(failure.message) }
    finally { writing.current = false; if (mounted.current) { setBusy(false); onBusy(false) } }
  }
  return <form onSubmit={save}>
    <SupplierError message={error} />
    <fieldset disabled={busy} className="m-0 grid min-w-0 grid-cols-2 gap-4 border-0 p-0">
      <Field id="supplier-code" label="Mã nhà cung cấp" required maxLength={50} value={form.SupplierCode} onChange={(event) => change('SupplierCode', event.target.value)} />
      <Field id="supplier-name" label="Tên nhà cung cấp" required maxLength={255} value={form.Name} onChange={(event) => change('Name', event.target.value)} />
      <Field id="supplier-phone" label="Số điện thoại" required type="tel" maxLength={20} value={form.PhoneNumber} onChange={(event) => change('PhoneNumber', event.target.value)} />
      <Field id="supplier-email" label="Email" type="email" maxLength={255} value={form.Email} onChange={(event) => change('Email', event.target.value)} />
      <Field id="supplier-tax" label="Mã số thuế" maxLength={20} value={form.TaxCode} onChange={(event) => change('TaxCode', event.target.value)} />
      <Field id="supplier-status" label="Trạng thái"><select id="supplier-status" className={PRODUCT_CONTROL} value={form.IsActive ? 'active' : 'hidden'} onChange={(event) => change('IsActive', event.target.value === 'active')}><option value="active">Hoạt động</option><option value="hidden">Ẩn</option></select></Field>
      <Field id="supplier-address" label="Địa chỉ" required className="col-span-full"><textarea id="supplier-address" required maxLength={500} rows={2} className={PRODUCT_CONTROL} value={form.Address} onChange={(event) => change('Address', event.target.value)} /></Field>
      <Field id="supplier-note" label="Ghi chú" className="col-span-full"><textarea id="supplier-note" maxLength={4000} rows={3} className={PRODUCT_CONTROL} value={form.Note} onChange={(event) => change('Note', event.target.value)} /></Field>
    </fieldset>
    <div className="mt-5 flex justify-end gap-2"><SupplierButton secondary disabled={busy} onClick={onClose}>Hủy</SupplierButton><SupplierButton type="submit" loading={busy}>{supplier ? 'Lưu thay đổi' : 'Thêm nhà cung cấp'}</SupplierButton></div>
  </form>
}

function SupplierDetails({ supplier, onEdit, onClose }) {
  const auth = useInternalAuth()
  return <>
    <h3 className="mb-4 text-lg font-semibold break-words">{supplier.Name}</h3>
    <dl className="m-0 grid grid-cols-2 gap-5">{[['Mã nhà cung cấp', supplier.SupplierCode], ['Trạng thái', <SupplierStatus key="status" active={supplier.IsActive} />], ['Số điện thoại', supplier.PhoneNumber], ['Email', supplier.Email], ['Mã số thuế', supplier.TaxCode], ['Địa chỉ', supplier.Address], ['Ghi chú', supplier.Note]].map(([label, value]) => <div key={label} className={['Địa chỉ', 'Ghi chú'].includes(label) ? 'col-span-full' : 'min-w-0'}><dt className="mb-1 text-xs text-admin-muted">{label}</dt><dd className="m-0 text-sm break-words whitespace-pre-wrap">{value || '—'}</dd></div>)}</dl>
    <div className="mt-6 flex justify-end gap-2"><SupplierButton secondary onClick={onClose}>Đóng</SupplierButton>{auth.permissions.includes('suppliers:update') && <SupplierButton onClick={onEdit}>Sửa nhà cung cấp</SupplierButton>}</div>
  </>
}

function SupplierHide({ supplier, onBusy, onClose, onDone }) {
  const auth = useInternalAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const writing = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  async function remove() {
    if (writing.current || !supplier.IsActive || !['suppliers:update', 'suppliers:delete'].every((permission) => auth.permissions.includes(permission))) return
    writing.current = true; setBusy(true); onBusy(true); setError('')
    try {
      await auth.withAccessToken((token) => hideSupplier(token, supplier.SupplierId))
      if (mounted.current) onDone('Đã ẩn nhà cung cấp.')
    } catch (failure) { if (mounted.current) setError(failure.message) }
    finally { writing.current = false; if (mounted.current) { setBusy(false); onBusy(false) } }
  }
  return <>
    <SupplierError message={error} />
    <p className="text-sm">Bạn muốn xóa mềm nhà cung cấp <strong className="break-words">{supplier.Name}</strong>?</p>
    <p className="mt-3 text-xs leading-relaxed text-admin-muted">Nhà cung cấp sẽ chuyển sang trạng thái Ẩn. Thông tin và liên kết với phiếu nhập, bảo hành được giữ lại. Bạn có thể mở lại bằng nút Sửa.</p>
    {!supplier.IsActive && <p role="status" className="mt-3 text-xs text-admin-muted">Nhà cung cấp này đã được ẩn.</p>}
    <div className="mt-6 flex justify-end gap-2"><SupplierButton secondary disabled={busy} onClick={onClose}>Hủy</SupplierButton><SupplierButton loading={busy} disabled={!supplier.IsActive} onClick={remove}>Xác nhận xóa mềm</SupplierButton></div>
  </>
}

export default function SupplierDialog({ mode, supplierId, onClose, onDone, onEdit }) {
  const auth = useInternalAuth()
  const allowed = mode === 'new' ? auth.permissions.includes('suppliers:create') : mode === 'edit' ? auth.permissions.includes('suppliers:update') : mode === 'delete' ? ['suppliers:update', 'suppliers:delete'].every((permission) => auth.permissions.includes(permission)) : mode === 'view' && auth.permissions.includes('suppliers:view')
  const detail = useAdminQuery('/admin/suppliers/' + encodeURIComponent(supplierId ?? ''), {}, allowed && mode !== 'new')
  const [busy, setBusy] = useState(false)
  if (!allowed) return null
  const title = { new: 'Thêm nhà cung cấp', edit: 'Sửa nhà cung cấp', view: 'Chi tiết nhà cung cấp', delete: 'Xóa mềm nhà cung cấp' }[mode]
  return <Modal open variant="tailwind" wide={mode !== 'delete'} title={title} busy={busy} onClose={onClose}>
    {mode !== 'new' && detail.loading ? <LoadingState label="Đang tải nhà cung cấp…" /> : mode !== 'new' && detail.error ? <ErrorState message={detail.error} onRetry={detail.refresh} /> : mode === 'view' && detail.data ? <SupplierDetails supplier={detail.data} onClose={onClose} onEdit={onEdit} /> : mode === 'delete' && detail.data ? <SupplierHide supplier={detail.data} onBusy={setBusy} onClose={onClose} onDone={onDone} /> : (mode === 'new' || detail.data) ? <SupplierEditor supplier={detail.data} onBusy={setBusy} onClose={onClose} onDone={onDone} /> : null}
  </Modal>
}
