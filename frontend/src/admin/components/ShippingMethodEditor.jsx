import { useState } from 'react'
import { ShippingButton } from './ShippingUi.jsx'

const BASE_CONTROL = 'h-[42px] w-full min-w-0 rounded-[10px] border border-admin-border bg-white px-[13px] text-xs leading-[normal] text-admin-text placeholder:text-admin-muted disabled:opacity-60'
function Field({ label, required, children }) {
  return <label className="flex min-w-0 flex-col gap-[7px] text-[11px] leading-[normal] font-semibold">{label}{required && ' *'}{children}</label>
}

export default function ShippingMethodEditor({ method, busy, error, onCancel, onSave }) {
  const CONTROL = BASE_CONTROL + (method ? ' font-medium' : ' font-normal')
  const [form, setForm] = useState(() => ({ Code: method?.Code ?? '', Name: method?.Name ?? '', BaseFee: method?.BaseFee ?? '', EstimatedDays: method?.EstimatedDays ?? '', IsActive: method?.IsActive ?? true }))
  const change = (key, value) => setForm((previous) => ({ ...previous, [key]: value }))
  return <form onSubmit={(event) => { event.preventDefault(); if (!busy) onSave(form) }}>
    <div className="flex min-h-[484px] flex-col gap-[15px] px-6 py-[18px]">
      <fieldset disabled={busy} className="m-0 flex min-w-0 flex-col gap-[15px] border-0 p-0">
        <Field label="Mã phương thức" required><input aria-label="Mã phương thức" type="text" required maxLength={50} placeholder="Ví dụ: STANDARD" className={CONTROL} value={form.Code} onChange={(event) => change('Code', event.target.value)} /></Field>
        <Field label="Tên phương thức" required><input aria-label="Tên phương thức" type="text" required maxLength={255} placeholder="Nhập tên phương thức vận chuyển" className={CONTROL} value={form.Name} onChange={(event) => change('Name', event.target.value)} /></Field>
        <Field label={method ? 'Phí vận chuyển cơ bản' : 'Phí vận chuyển'} required><span className="relative block"><input aria-label={method ? 'Phí vận chuyển cơ bản' : 'Phí vận chuyển'} type="number" required min="0" max="9999999999999.99" step="0.01" placeholder="0" className={CONTROL + ' pr-[58px] [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'} value={form.BaseFee} onChange={(event) => change('BaseFee', event.target.value)} /><span className="pointer-events-none absolute top-0 right-[13px] flex h-full items-center text-[11px] font-medium text-admin-muted" aria-hidden="true">VNĐ</span></span></Field>
        <Field label="Số ngày giao dự kiến" required><span className="relative block"><input aria-label="Số ngày giao dự kiến" title="Từ 0 đến 30 ngày; 0 là giao trong ngày." type="number" required min="0" max="30" step="1" placeholder="Ví dụ: 3" className={CONTROL + ' pr-[58px] [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'} value={form.EstimatedDays} onChange={(event) => change('EstimatedDays', event.target.value)} /><span className="pointer-events-none absolute top-0 right-[13px] flex h-full items-center text-[11px] font-medium text-admin-muted" aria-hidden="true">ngày</span></span></Field>
        <Field label="Trạng thái"><span className="relative block"><select aria-label="Trạng thái" className={CONTROL + ' appearance-none pr-9 font-medium'} value={String(form.IsActive)} onChange={(event) => change('IsActive', event.target.value === 'true')}><option value="true">Đang hoạt động</option><option value="false">Ngừng hoạt động</option></select><span aria-hidden="true" className="pointer-events-none absolute top-0 right-[13px] flex h-full items-center text-xs font-medium text-admin-muted">▾</span></span></Field>
      </fieldset>
      <p className="m-0 min-h-7 text-[10px] leading-[normal] text-admin-muted">{method ? 'Thay đổi sẽ được áp dụng cho các đơn hàng tạo sau thời điểm cập nhật.' : 'Các trường có dấu * là bắt buộc. Mã phương thức không được trùng.'}</p>
      {error && <p role="alert" className="m-0 text-xs text-admin-red">{error}</p>}
    </div>
    <div className="flex min-h-[72px] items-center justify-end gap-2.5 px-6 py-4"><ShippingButton secondary className="w-[88px]" disabled={busy} onClick={onCancel}>Hủy</ShippingButton><ShippingButton className="w-[140px]" type="submit" disabled={busy}>{busy ? 'Đang lưu…' : method ? 'Lưu thay đổi' : 'Thêm phương thức'}</ShippingButton></div>
  </form>
}
