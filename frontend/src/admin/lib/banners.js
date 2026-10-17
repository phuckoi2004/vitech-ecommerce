import { VIETNAM_TIME_ZONE } from '../../lib/format.js'

export const BANNER_PAGE_SIZE = 5
export const BANNER_STATUSES = { active: 'Hoạt động', inactive: 'Ngừng hoạt động' }
export const BANNER_PAGE_TITLES = { view: 'Chi tiết banner quảng cáo', new: 'Thêm banner quảng cáo', edit: 'Sửa banner quảng cáo' }
export function bannerSearch(params) {
  const next = new URLSearchParams(params)
  next.delete('dialog'); next.delete('banner')
  return next.size ? '?' + next.toString() : ''
}
export function bannerPagePath(mode, id, params) {
  return '/admin/banners' + (mode === 'new' ? '/new' : '/' + encodeURIComponent(id) + (mode === 'edit' ? '/edit' : '')) + bannerSearch(params)
}
export function bannerFilter(params) {
  const page = Number(params.get('page'))
  return { keyword: (params.get('keyword') ?? '').trim().slice(0, 255), status: Object.hasOwn(BANNER_STATUSES, params.get('status')) ? params.get('status') : '', page: Number.isSafeInteger(page) && page > 0 ? page : 1 }
}

// Destination links may be internal paths or HTTPS URLs. Image URLs come from uploads only.
export function safeBannerLink(value) {
  const link = typeof value === 'string' ? value.trim() : ''
  if (!link || /[\s\\]/.test(link) || Array.from(link).some((char) => char.codePointAt(0) < 32 || char.codePointAt(0) === 127)) return null
  if (link.startsWith('/') && !link.startsWith('//')) return link
  try { const url = new URL(link); return url.protocol === 'https:' && url.hostname && !url.username && !url.password ? link : null } catch { return null }
}

const clock = new Intl.DateTimeFormat('en-GB', { timeZone: VIETNAM_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
export function bannerInputTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const parts = Object.fromEntries(clock.formatToParts(date).map((part) => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`
}
export function bannerPayload(form, banner) {
  const time = (field) => !form[field] ? null : banner && form[field] === bannerInputTime(banner[field]) ? banner[field] : form[field] + '+07:00'
  return { Title: form.Title.trim(), ImageUrl: form.ImageUrl, LinkUrl: form.LinkUrl.trim() || null, DisplayOrder: form.DisplayOrder.trim() ? Number(form.DisplayOrder) : NaN, StartDate: time('StartDate'), EndDate: time('EndDate') }
}
export function bannerValidation(body) {
  if (!body.Title) return 'Vui lòng nhập tiêu đề banner.'
  if (!body.ImageUrl) return 'Vui lòng chọn ảnh banner (tải từ máy hoặc dán đường dẫn) và chờ tải lên hoàn tất.'
  if (body.LinkUrl && !safeBannerLink(body.LinkUrl)) return 'Link khi bấm phải là đường dẫn nội bộ bắt đầu bằng / hoặc địa chỉ HTTPS hợp lệ.'
  if (!Number.isSafeInteger(body.DisplayOrder)) return 'Thứ tự hiển thị phải là số nguyên.'
  if ([body.StartDate, body.EndDate].some((value) => value && Number.isNaN(new Date(value).getTime()))) return 'Vui lòng chọn thời gian hiển thị hợp lệ.'
  if (body.StartDate && body.EndDate && new Date(body.EndDate) < new Date(body.StartDate)) return 'Thời điểm kết thúc phải sau hoặc bằng thời điểm bắt đầu.'
  return ''
}
