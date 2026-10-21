import { formatStatus } from './status-labels.js'

// Display stages shared by customers and operators; these are derived from existing API fields.
export const WARRANTY_STATUSES = [
  ['New', 'Mới'], ['Inspecting', 'Đang kiểm tra'], ['Repairing', 'Đang sửa'],
  ['Finished', 'Hoàn tất'], ['Returned', 'Đã trả khách'], ['Rejected', 'Từ chối'], ['Cancelled', 'Đã hủy'],
]

export function warrantyStage(item) {
  if (item.Status === 'New') return item.ReceivedAt ? 'Inspecting' : 'New'
  if (['HandedOver', 'Processing'].includes(item.Status)) return item.ResultApprovedAt ? 'Finished' : 'Repairing'
  return item.Status === 'Completed' ? 'Returned' : item.Status
}

export const warrantyStageLabel = (stage) => WARRANTY_STATUSES.find(([key]) => key === stage)?.[1] ?? formatStatus(stage)
export const warrantyResultLabel = (result) => formatStatus(result, { Repaired: 'Đã sửa chữa', ProductReplaced: 'Đổi máy', PartReplaced: 'Thay linh kiện', NotRepairable: 'Không thể sửa chữa' })
export const canCancelWarranty = (item) => item.Status === 'New' && !item.ReceivedAt
