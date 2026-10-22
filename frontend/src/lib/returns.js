import { formatStatus } from './status-labels.js'

export const RETURN_STATUSES = [
  ['Pending', 'Đang chờ'], ['Approved', 'Đã tiếp nhận'], ['Receiving', 'Đang điều phối'],
  ['Processing', 'Đang đánh giá hư hại'], ['Completed', 'Hoàn tất'], ['Rejected', 'Từ chối'], ['Cancelled', 'Đã hủy'],
]
export const returnStatusLabel = (status) => RETURN_STATUSES.find(([key]) => key === status)?.[1] ?? formatStatus(status)
export const returnTypeLabel = (type) => ({ Exchange: 'Đổi', Return: 'Trả' })[type] ?? type
export const canCancelReturn = (item) => ['Pending', 'Approved', 'Receiving', 'Processing'].includes(item.Status) && !item.Exchange?.Committed
