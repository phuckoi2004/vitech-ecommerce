import { formatDate } from '../../lib/format.js'
import { formatStatus } from '../../lib/status-labels.js'

export const WARRANTY_PAGE_SIZE = 6
export const WARRANTY_RESULTS = [['Repaired', 'Sửa chữa'], ['PartReplaced', 'Thay linh kiện'], ['NotRepairable', 'Không thể sửa chữa']]
export const WARRANTY_STATUSES = [
  ['New', 'Mới'], ['Inspecting', 'Đang kiểm tra'], ['Repairing', 'Đang sửa'],
  ['Finished', 'Hoàn tất'], ['Returned', 'Đã trả khách'], ['Rejected', 'Từ chối'], ['Cancelled', 'Đã hủy'],
]
// These are display stages derived from existing API fields, not new database statuses.
export function warrantyStage(item) {
  if (item.Status === 'New') return item.ReceivedAt ? 'Inspecting' : 'New'
  if (item.Status === 'HandedOver') return item.ResultApprovedAt ? 'Finished' : 'Repairing'
  if (item.Status === 'Processing') return item.ResultApprovedAt ? 'Finished' : 'Repairing'
  if (item.Status === 'Completed') return 'Returned'
  return item.Status
}
export const warrantyStageLabel = (stage) => WARRANTY_STATUSES.find(([key]) => key === stage)?.[1] ?? formatStatus(stage)
export const warrantyHistoryLabel = (status) => formatStatus(status, { New: 'Tiếp nhận / kiểm tra', HandedOver: 'Đã bàn giao trung tâm bảo hành', Processing: 'Đang xử lý', Completed: 'Đã trả khách', Rejected: 'Từ chối', Cancelled: 'Đã hủy' })
export const warrantyResultLabel = (result) => formatStatus(result, { Repaired: 'Đã sửa chữa', ProductReplaced: 'Đổi máy', PartReplaced: 'Thay linh kiện', NotRepairable: 'Không thể sửa chữa' })
export const warrantySerialLabel = (serial) => /^\d{15}$/.test(serial ?? '') ? serial.slice(0, 4) + '••••' + serial.slice(-4) : serial || '—'
const validDay = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value ?? '') && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
const fold = (value) => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLowerCase()
export function warrantyFilters(params) {
  const rawPage = Number(params.get('page'))
  return {
    keyword: params.get('keyword')?.trim() || '',
    status: WARRANTY_STATUSES.some(([key]) => key === params.get('status')) ? params.get('status') : '',
    from: validDay(params.get('from')) ? params.get('from') : '',
    to: validDay(params.get('to')) ? params.get('to') : '',
    page: Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1,
  }
}
export function filterWarranties(rows, filter) {
  const term = fold(filter.keyword)
  return rows.filter((row) => {
    const day = formatDate(row.RequestedAt).split('/').reverse().join('-')
    return (!filter.status || warrantyStage(row) === filter.status) && (!filter.from || day >= filter.from) && (!filter.to || day <= filter.to)
      && (!term || [row.RequestCode, row.CustomerName, row.ProductName, row.Sku, row.SerialNumber, row.OrderCode].some((value) => fold(value).includes(term)))
  }).sort((a, b) => (Date.parse(b.RequestedAt) || 0) - (Date.parse(a.RequestedAt) || 0)
    || a.WarrantyRequestId.localeCompare(b.WarrantyRequestId))
}
export function warrantyListSearch(params) {
  const next = new URLSearchParams(params)
  for (const key of [...next.keys()]) if (!['keyword', 'status', 'from', 'to', 'page'].includes(key)) next.delete(key)
  return next.size ? '?' + next : ''
}
