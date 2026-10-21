import { formatDate } from '../../lib/format.js'
import { RETURN_STATUSES } from '../../lib/returns.js'
export { RETURN_STATUSES, returnStatusLabel, returnTypeLabel } from '../../lib/returns.js'

export const RETURN_PAGE_SIZE = 6
const validDay = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value ?? '') && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
const fold = (value) => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLowerCase()
export function returnFilters(params) {
  const rawPage = Number(params.get('page'))
  return {
    keyword: params.get('keyword')?.trim() || '',
    status: RETURN_STATUSES.some(([key]) => key === params.get('status')) ? params.get('status') : '',
    from: validDay(params.get('from')) ? params.get('from') : '',
    to: validDay(params.get('to')) ? params.get('to') : '',
    page: Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1,
  }
}
export function filterReturns(rows, filter) {
  const term = fold(filter.keyword)
  return rows.filter((row) => {
    const day = formatDate(row.RequestedAt).split('/').reverse().join('-')
    return (!filter.status || row.Status === filter.status) && (!filter.from || day >= filter.from) && (!filter.to || day <= filter.to)
      && (!term || [row.RequestCode, row.CustomerName, row.ProductName, row.Sku, row.VariantInfo, row.OrderCode].some((value) => fold(value).includes(term)))
  }).sort((a, b) => Number(b.Status === 'Pending') - Number(a.Status === 'Pending')
    || (Date.parse(b.RequestedAt) || 0) - (Date.parse(a.RequestedAt) || 0)
    || a.ReturnRequestId.localeCompare(b.ReturnRequestId))
}
export function returnListSearch(params) {
  const next = new URLSearchParams(params)
  for (const key of [...next.keys()]) if (!['keyword', 'status', 'from', 'to', 'page'].includes(key)) next.delete(key)
  return next.size ? '?' + next : ''
}
