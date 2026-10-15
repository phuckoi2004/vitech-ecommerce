import { useState } from 'react'
import { slugFromName } from '../../lib/admin-products.js'
import { NEWS_STATUSES, newsStatusChoices } from '../lib/news.js'
import AdminImagePicker from './AdminImagePicker.jsx'
import { NewsButton } from './NewsUi.jsx'

const CONTROL = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] leading-3 text-admin-text placeholder:text-admin-text'
function Field({ label, children }) { return <label className="flex min-w-0 flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">{label}{children}</label> }

export default function NewsEditor({ article, currentStatus, canChangeStatus, busy, onUploadBusy, onCancel, onSave }) {
  const [form, setForm] = useState(() => ({ Title: article?.Title ?? '', Slug: article?.Slug ?? '', Summary: article?.Summary ?? '', Content: article?.Content ?? '', ThumbnailUrl: article?.ThumbnailUrl ?? '', Status: article?.Status ?? 'Draft' }))
  const [editedSlug, setEditedSlug] = useState(Boolean(article))
  function change(key, value) {
    setForm((previous) => ({ ...previous, [key]: value, ...(key === 'Title' && !editedSlug ? { Slug: slugFromName(value) } : {}) }))
    if (key === 'Slug') setEditedSlug(true)
  }
  function submit(event) {
    event.preventDefault()
    if (!busy) onSave({ Title: form.Title.trim(), Slug: form.Slug.trim(), Summary: form.Summary.trim() || null, Content: form.Content.trim(), ThumbnailUrl: form.ThumbnailUrl || null }, form.Status)
  }
  const statuses = canChangeStatus ? newsStatusChoices(currentStatus) : [currentStatus]
  return <form onSubmit={submit} className="flex flex-col gap-3">
    <fieldset disabled={busy} className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
      <Field label="Tiêu đề"><input aria-label="Tiêu đề" className={CONTROL} required maxLength={255} placeholder="Nhập tiêu đề bài viết" value={form.Title} onChange={(event) => change('Title', event.target.value)} /></Field>
      <Field label="Slug"><input aria-label="Slug" className={CONTROL} required maxLength={300} pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="Nhập đường dẫn SEO" value={form.Slug} onChange={(event) => change('Slug', event.target.value)} /></Field>
      <Field label="Tóm tắt"><textarea aria-label="Tóm tắt" className={CONTROL + ' h-[70px]! resize-y py-2.5'} placeholder="Nhập tóm tắt bài viết" value={form.Summary} onChange={(event) => change('Summary', event.target.value)} /></Field>
      <AdminImagePicker variant="news" title="Ảnh đại diện" name="tin tức" multiple={false} images={form.ThumbnailUrl ? [{ ImageUrl: form.ThumbnailUrl, IsDefault: true }] : []} onChange={(images) => change('ThumbnailUrl', images[0]?.ImageUrl ?? '')} onUploadBusy={onUploadBusy} disabled={busy} />
      <Field label="Trạng thái"><select aria-label="Trạng thái" className={CONTROL} value={form.Status} disabled={busy || !canChangeStatus} onChange={(event) => change('Status', event.target.value)}>{statuses.map((value) => <option key={value} value={value}>{NEWS_STATUSES[value]}</option>)}</select></Field>
      <Field label="Nội dung"><textarea aria-label="Nội dung" className={CONTROL + ' h-[150px]! resize-y py-2.5'} required placeholder="Nhập nội dung bài viết" value={form.Content} onChange={(event) => change('Content', event.target.value)} /></Field>
    </fieldset>
    <div className="flex justify-end"><NewsButton secondary className="text-admin-text!" disabled={busy} onClick={onCancel}>Hủy</NewsButton><NewsButton type="submit" loading={busy}>{article ? 'Cập nhật' : 'Lưu tin tức'}</NewsButton></div>
  </form>
}
