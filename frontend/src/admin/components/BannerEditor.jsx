import { useState } from 'react'
import { BANNER_STATUSES, bannerInputTime, bannerPayload } from '../lib/banners.js'
import AdminImagePicker from './AdminImagePicker.jsx'
import { BannerButton } from './BannerUi.jsx'

const CONTROL = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] leading-3 text-admin-text placeholder:text-admin-text'
function Field({ label, children }) { return <label className="flex min-w-0 flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">{label}{children}</label> }
export default function BannerEditor({ banner, busy, canChangeStatus, onUploadBusy, onCancel, onSave }) {
  const [form, setForm] = useState(() => ({ Title: banner?.Title ?? '', ImageUrl: banner?.ImageUrl ?? '', LinkUrl: banner?.LinkUrl ?? '', DisplayOrder: String(banner?.DisplayOrder ?? 0), StartDate: bannerInputTime(banner?.StartDate), EndDate: bannerInputTime(banner?.EndDate), Status: banner?.IsActive === false ? 'inactive' : 'active' }))
  const change = (field, value) => setForm((previous) => ({ ...previous, [field]: value }))
  return <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); if (!busy) onSave(bannerPayload(form, banner), form.Status === 'active') }}>
    <fieldset disabled={busy} className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
      <Field label="Tiêu đề"><input aria-label="Tiêu đề" className={CONTROL} required maxLength={255} placeholder="Nhập tiêu đề banner" value={form.Title} onChange={(event) => change('Title', event.target.value)} /></Field>
      <AdminImagePicker variant="compact" title="Ảnh banner" name="banner" multiple={false} images={form.ImageUrl ? [{ ImageUrl: form.ImageUrl, IsDefault: true }] : []} onChange={(images) => change('ImageUrl', images[0]?.ImageUrl ?? '')} onUploadBusy={onUploadBusy} disabled={busy} />
      <Field label="Link khi bấm"><input aria-label="Link khi bấm" className={CONTROL} maxLength={500} placeholder="Nhập đường dẫn liên kết" value={form.LinkUrl} onChange={(event) => change('LinkUrl', event.target.value)} /></Field>
      <Field label="Thứ tự hiển thị"><input aria-label="Thứ tự hiển thị" type="number" step="1" required className={CONTROL} placeholder="Nhập thứ tự" value={form.DisplayOrder} onChange={(event) => change('DisplayOrder', event.target.value)} /></Field>
      <Field label="Bắt đầu hiển thị"><input aria-label="Bắt đầu hiển thị" type="datetime-local" step="1" className={CONTROL} value={form.StartDate} onChange={(event) => change('StartDate', event.target.value)} /></Field>
      <Field label="Kết thúc hiển thị"><input aria-label="Kết thúc hiển thị" type="datetime-local" step="1" className={CONTROL} value={form.EndDate} onChange={(event) => change('EndDate', event.target.value)} /></Field>
      <Field label="Trạng thái"><select aria-label="Trạng thái" className={CONTROL} value={form.Status} disabled={busy || !canChangeStatus} onChange={(event) => change('Status', event.target.value)}>{Object.entries(BANNER_STATUSES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
    </fieldset>
    <p className="m-0 text-[9px] leading-3 text-admin-muted">Giờ Việt Nam (UTC+7). Để trống mốc thời gian nếu không giới hạn. Thứ tự nhỏ hơn được hiển thị trước.</p>
    <div className="flex justify-end"><BannerButton secondary className="text-admin-text!" disabled={busy} onClick={onCancel}>Hủy</BannerButton><BannerButton type="submit" loading={busy}>{banner ? 'Cập nhật' : 'Lưu banner'}</BannerButton></div>
  </form>
}
