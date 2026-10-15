import { NEWS_STATUSES, newsPublishedTime } from '../lib/news.js'
import { NewsButton } from './NewsUi.jsx'

const CONTROL = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] leading-3 text-admin-text'
function Field({ label, value, height }) {
  return <label className="flex min-w-0 flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">{label}{height ? <textarea aria-label={label} readOnly value={value || '—'} className={CONTROL + ' resize-none py-2.5 ' + height} /> : <input aria-label={label} readOnly value={value || '—'} className={CONTROL} />}</label>
}
export default function NewsDetail({ article, busy, canEdit, onClose, onEdit, onStatus }) {
  return <div className="flex flex-col gap-3">
    <Field label="Tiêu đề" value={article.Title} /><Field label="Slug" value={article.Slug} />
    <Field label="Tóm tắt" value={article.Summary} height="h-[70px]!" />
    <section aria-label="Ảnh đại diện" className="flex flex-col gap-[5px]"><h3 className="m-0 text-[9px] leading-[11px] font-medium text-admin-muted">Ảnh đại diện</h3><div className="flex min-h-[38px] items-center rounded-lg border border-admin-border px-2.5 py-[3px]">{article.ThumbnailUrl ? <img src={article.ThumbnailUrl} alt="Ảnh đại diện tin tức" className="h-[30px] max-w-full rounded object-contain" /> : <span className="text-[9px] text-admin-muted">Chưa có ảnh đại diện</span>}</div></section>
    <Field label="Trạng thái" value={NEWS_STATUSES[article.Status] ?? article.Status} />
    <Field label="Thời điểm đăng" value={newsPublishedTime(article.PublishedAt)} />
    <Field label="Nội dung" value={article.Content} height="h-[120px]!" />
    <div className="flex justify-end">{canEdit && <><NewsButton secondary disabled={busy} onClick={onEdit}>Sửa tin tức</NewsButton><NewsButton secondary disabled={busy} onClick={onStatus}>{article.Status === 'Published' ? 'Ẩn bài viết' : 'Đăng bài viết'}</NewsButton></>}<NewsButton secondary className="text-admin-text!" disabled={busy} onClick={onClose}>Hủy</NewsButton><NewsButton loading={busy} onClick={onClose}>Đóng</NewsButton></div>
  </div>
}
