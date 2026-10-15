import { formatDateTime } from '../../lib/format.js'
import { BANNER_STATUSES } from '../lib/banners.js'
import { BannerButton, BannerImage, BannerLink } from './BannerUi.jsx'

const CONTROL = 'h-[38px] w-full rounded-lg border border-admin-border bg-white px-2.5 text-[9px] leading-3 text-admin-text'
function Field({ label, value }) { return <label className="flex min-w-0 flex-col gap-[5px] text-[9px] leading-[11px] font-medium text-admin-muted">{label}<input aria-label={label} readOnly value={value ?? '—'} className={CONTROL} /></label> }
export default function BannerDetail({ banner, busy, canEdit, onClose, onEdit, onStatus }) {
  function time(value) {
    if (!value) return 'Không giới hạn'
    const formatted = formatDateTime(value)
    if (formatted === '—') return formatted
    const [clock, date] = formatted.split(' ')
    return date + ' ' + clock
  }
  return <div className="flex flex-col gap-3">
    <Field label="Tiêu đề" value={banner.Title} />
    <section aria-label="Ảnh banner" className="flex min-w-0 flex-col gap-[5px]"><h3 className="m-0 text-[9px] leading-[11px] font-medium text-admin-muted">Ảnh banner</h3><div className="flex h-[38px] items-center rounded-lg border border-admin-border px-2.5"><BannerImage src={banner.ImageUrl} title={banner.Title} compact /></div></section>
    <section aria-label="Link khi bấm" className="flex min-w-0 flex-col gap-[5px]"><h3 className="m-0 text-[9px] leading-[11px] font-medium text-admin-muted">Link khi bấm</h3><div className={CONTROL + ' flex items-center overflow-auto'}><BannerLink value={banner.LinkUrl} /></div></section>
    <Field label="Thứ tự hiển thị" value={banner.DisplayOrder} />
    <Field label="Bắt đầu hiển thị" value={time(banner.StartDate)} />
    <Field label="Kết thúc hiển thị" value={time(banner.EndDate)} />
    <Field label="Trạng thái" value={BANNER_STATUSES[banner.IsActive ? 'active' : 'inactive']} />
    <div className="flex justify-end">{canEdit && <><BannerButton secondary disabled={busy} onClick={onEdit}>Sửa banner</BannerButton><BannerButton secondary disabled={busy} onClick={onStatus}>{banner.IsActive ? 'Ngừng hoạt động' : 'Bật banner'}</BannerButton></>}<BannerButton secondary className="text-admin-text!" disabled={busy} onClick={onClose}>Hủy</BannerButton><BannerButton loading={busy} onClick={onClose}>Đóng</BannerButton></div>
  </div>
}
