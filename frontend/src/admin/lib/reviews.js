import { formatDate, formatDateTime } from '../../lib/format.js'

export const REVIEW_PAGE_SIZE = 5
export const REVIEW_PERIODS = [['', 'Tất cả thời gian'], ['today', 'Hôm nay'], ['7days', '7 ngày qua'], ['30days', '30 ngày qua'], ['month', 'Tháng này']]

export function reviewFilters(params) {
  const page = Number(params.get('page'))
  return { period: REVIEW_PERIODS.some(([value]) => value === params.get('period')) ? params.get('period') : '', rating: /^[1-5]$/.test(params.get('rating') ?? '') ? params.get('rating') : '', page: Number.isSafeInteger(page) && page > 0 ? page : 1 }
}
function day(value) { return formatDate(value).split('/').reverse().join('-') }
export function filterReviews(rows, filter, now = new Date()) {
  const today = day(now)
  let start = ''
  if (filter.period === 'today') start = today
  if (filter.period === 'month') start = today.slice(0, 7) + '-01'
  if (['7days', '30days'].includes(filter.period)) {
    const date = new Date(today + 'T00:00:00Z')
    date.setUTCDate(date.getUTCDate() - (filter.period === '7days' ? 6 : 29))
    start = date.toISOString().slice(0, 10)
  }
  return rows.filter((review) => (!filter.rating || review.Rating === Number(filter.rating)) && (!start || (day(review.CreatedAt) >= start && day(review.CreatedAt) <= today)))
}
export function reviewTimestamp(value) { const date = formatDate(value); return date === '—' ? '—' : date + ' ' + formatDateTime(value).slice(0, 5) }
export function reviewImageUrl(value) { return typeof value === 'string' && (/^https?:\/\//i.test(value) || /^\/(?!\/)/.test(value)) ? value : null }
