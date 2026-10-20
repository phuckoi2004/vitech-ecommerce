import { useState } from 'react'
import useInternalAuth from '../../hooks/useInternalAuth.js'
import { slugFromName } from '../../lib/admin-products.js'
import { normalizeRichText } from '../../lib/rich-text.js'
import { NEWS_STATUSES, newsStatusChoices } from '../lib/news.js'
import { uploadProductImage } from '../services/product-media.js'
import AdminImagePicker from './AdminImagePicker.jsx'
import { NewsButton } from './NewsUi.jsx'
import RichTextEditor from './RichTextEditor.jsx'

const CONTROL = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] leading-3 text-admin-text placeholder:text-admin-text'
function Field({ label, children }) { return <label className="flex min-w-0 flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">{label}{children}</label> }

export default function NewsEditor({ article, currentStatus, canChangeStatus, busy, onUploadBusy, onCancel, onSave }) {
  const { withAccessToken } = useInternalAuth()
  const [form, setForm] = useState(() => ({ Title: article?.Title ?? '', Slug: article?.Slug ?? '', Summary: article?.Summary ?? '', Content: article?.Content ?? '', ThumbnailUrl: article?.ThumbnailUrl ?? '', Status: article?.Status ?? 'Draft' }))
  const [editedSlug, setEditedSlug] = useState(Boolean(article))
  function change(key, value) {
    setForm((previous) => ({ ...previous, [key]: value, ...(key === 'Title' && !editedSlug ? { Slug: slugFromName(value) } : {}) }))
    if (key === 'Slug') setEditedSlug(true)
  }
  function submit(event) {
    event.preventDefault()
    if (!busy) onSave({ Title: form.Title.trim(), Slug: form.Slug.trim(), Summary: form.Summary.trim() || null, Content: normalizeRichText(form.Content) ?? '', ThumbnailUrl: form.ThumbnailUrl || null }, form.Status)
  }
  async function uploadContentImage(file) {
    const result = await withAccessToken(token => uploadProductImage(token, file))
    if (!result?.ImageUrl) throw new Error('Máy chủ chưa trả về ảnh đã tải lên. Vui lòng thử lại.')
    return result.ImageUrl
  }
  const statuses = canChangeStatus ? newsStatusChoices(currentStatus) : [currentStatus]
  return <form onSubmit={submit} className="flex flex-col gap-3">
    <fieldset disabled={busy} className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
      <Field label="Tiêu đề"><input aria-label="Tiêu đề" className={CONTROL} required maxLength={255} placeholder="Nhập tiêu đề bài viết" value={form.Title} onChange={(event) => change('Title', event.target.value)} /></Field>
      <Field label="Slug"><input aria-label="Slug" className={CONTROL} required maxLength={300} pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="Nhập đường dẫn SEO" value={form.Slug} onChange={(event) => change('Slug', event.target.value)} /></Field>
      <Field label="Tóm tắt"><textarea aria-label="Tóm tắt" className={CONTROL + ' h-[70px]! resize-y py-2.5'} placeholder="Nhập tóm tắt bài viết" value={form.Summary} onChange={(event) => change('Summary', event.target.value)} /></Field>
      <AdminImagePicker variant="news" secureOnly title="Ảnh đại diện" name="tin tức" multiple={false} images={form.ThumbnailUrl ? [{ ImageUrl: form.ThumbnailUrl, IsDefault: true }] : []} onChange={(images) => change('ThumbnailUrl', images[0]?.ImageUrl ?? '')} onUploadBusy={onUploadBusy} disabled={busy} />
      <Field label="Trạng thái"><select aria-label="Trạng thái" className={CONTROL} value={form.Status} disabled={busy || !canChangeStatus} onChange={(event) => change('Status', event.target.value)}>{statuses.map((value) => <option key={value} value={value}>{NEWS_STATUSES[value]}</option>)}</select></Field>
      <RichTextEditor id="news-content" label="Nội dung" labelClassName="text-sm font-medium text-admin-text" value={form.Content} onChange={(value) => change('Content', value)} disabled={busy}
        placeholder="Nhập nội dung bài viết…" toolbarLabel="Định dạng nội dung tin tức" imageUploadLabel="Chọn ảnh để chèn vào nội dung" emptyText="Chưa có nội dung bài viết."
        hint="Bôi đen chữ để chọn phông, cỡ chữ hoặc định dạng. Có thể chèn liên kết, kéo thả hoặc dán ảnh vào nội dung."
        onUploadImage={uploadContentImage} onUploadBusy={onUploadBusy} />
    </fieldset>
    <div className="flex justify-end"><NewsButton secondary className="text-admin-text!" disabled={busy} onClick={onCancel}>Hủy</NewsButton><NewsButton type="submit" loading={busy}>{article ? 'Cập nhật' : 'Lưu tin tức'}</NewsButton></div>
  </form>
}
