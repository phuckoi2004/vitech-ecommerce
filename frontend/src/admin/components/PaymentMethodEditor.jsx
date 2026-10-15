import { useState } from 'react'
import { PaymentButton } from './PaymentMethodUi.jsx'

const CONTROL = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] leading-3 text-admin-text placeholder:text-admin-text'
function Field({ label, required, children }) { return <label className="flex min-w-0 flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">{label}{required && ' *'}{children}</label> }

export default function PaymentMethodEditor({ method, busy, validation, onCancel, onSave }) {
  const [form, setForm] = useState(() => ({ Code: method?.Code ?? '', Name: method?.Name ?? '', Description: method?.Description ?? '', IsActive: method?.IsActive ?? true, DisplayOrder: String(method?.DisplayOrder ?? 0) }))
  const change = (field, value) => setForm((previous) => ({ ...previous, [field]: value }))
  function submit(event) {
    event.preventDefault()
    if (busy) return
    // The current backend uses the existing code to identify COD processing. Keep it intact when editing.
    onSave({ ...(!method ? { Code: form.Code.trim().toUpperCase() } : {}), Name: form.Name.trim(), Description: form.Description.trim() || null, IsActive: form.IsActive, DisplayOrder: form.DisplayOrder.trim() ? Number(form.DisplayOrder) : NaN })
  }
  return <form className="flex flex-col gap-3" onSubmit={submit}>
    {validation && <p role="alert" className="m-0 text-[10px] leading-3 text-admin-red">{validation}</p>}
    <fieldset disabled={busy} className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
      <Field label="Mã phương thức" required><input aria-label="Mã phương thức" required maxLength={50} readOnly={Boolean(method)} title={method ? 'Mã nhận diện cách xử lý thanh toán và được giữ nguyên khi sửa.' : undefined} placeholder="Ví dụ: COD, QR" className={CONTROL} value={form.Code} onChange={(event) => change('Code', event.target.value)} /></Field>
      <Field label="Tên phương thức" required><input aria-label="Tên phương thức" required maxLength={255} placeholder="Nhập tên phương thức thanh toán" className={CONTROL} value={form.Name} onChange={(event) => change('Name', event.target.value)} /></Field>
      <Field label="Mô tả / hướng dẫn"><textarea aria-label="Mô tả / hướng dẫn" placeholder="Nhập mô tả hoặc hướng dẫn thanh toán" className={CONTROL + ' h-[110px]! resize-y py-2.5'} value={form.Description} onChange={(event) => change('Description', event.target.value)} /></Field>
      <Field label="Trạng thái" required><select aria-label="Trạng thái" required className={CONTROL} value={form.IsActive ? 'active' : 'inactive'} onChange={(event) => change('IsActive', event.target.value === 'active')}><option value="active">Hoạt động</option><option value="inactive">Ngừng hoạt động</option></select></Field>
      <Field label="Thứ tự hiển thị" required><input aria-label="Thứ tự hiển thị" type="number" step="1" min="-2147483648" max="2147483647" required placeholder="Nhập thứ tự hiển thị" className={CONTROL} value={form.DisplayOrder} onChange={(event) => change('DisplayOrder', event.target.value)} /></Field>
    </fieldset>
    <div className="flex justify-end"><PaymentButton secondary className="text-admin-text!" disabled={busy} onClick={onCancel}>Hủy</PaymentButton><PaymentButton type="submit" loading={busy}>{method ? 'Cập nhật' : 'Lưu phương thức'}</PaymentButton></div>
  </form>
}
