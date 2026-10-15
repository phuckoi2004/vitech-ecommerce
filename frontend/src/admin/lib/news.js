import { formatDateTime } from '../../lib/format.js'

export const NEWS_PAGE_SIZE = 5
export const NEWS_STATUSES = { Published: 'Đã đăng', Draft: 'Nháp', Hidden: 'Đã ẩn' }
export const NEWS_PAGE_TITLES = { view: 'Chi tiết tin tức', new: 'Thêm tin tức', edit: 'Sửa tin tức' }
export function newsSearch(params) {
  const next = new URLSearchParams(params)
  next.delete('dialog'); next.delete('article')
  return next.size ? '?' + next.toString() : ''
}
export function newsPagePath(mode, id, params) {
  const base = '/admin/news' + (mode === 'new' ? '/new' : '/' + encodeURIComponent(id) + (mode === 'edit' ? '/edit' : ''))
  return base + newsSearch(params)
}
export function newsStatusChoices(current = 'Draft') {
  return current === 'Draft' ? ['Draft', 'Published'] : ['Published', 'Hidden']
}
export function newsFilter(params) {
  const rawPage = Number(params.get('page'))
  return { keyword: (params.get('keyword') ?? '').trim().slice(0, 300), status: Object.hasOwn(NEWS_STATUSES, params.get('status')) ? params.get('status') : '', page: Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1 }
}
export function newsPublishedTime(value) {
  if (!value) return '—'
  const text = formatDateTime(value)
  if (text === '—') return text
  const [time, date] = text.split(' ')
  return date + ' ' + time
}
