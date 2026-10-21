import { safeNext } from '../auth/session.js'
import { formatStatus } from '../lib/status-labels.js'
import { CHAT_PATH, HOME_PATH, INFO_PATHS, NEWS_PATH, SEARCH_PATH, CART_PATH, WISHLIST_PATH, NOTIFICATIONS_PATH, ACCOUNT_PATH } from './routes/paths.js'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const RESOURCES = {
  Order: ['/orders/', 'Chi tiết đơn hàng'],
  WarrantyRequest: ['/warranty-requests/', 'Chi tiết bảo hành'],
  ReturnRequest: ['/return-requests/', 'Chi tiết đổi trả'],
}
const PAGES = new Set([HOME_PATH, SEARCH_PATH, CART_PATH, WISHLIST_PATH, NOTIFICATIONS_PATH, ACCOUNT_PATH, CHAT_PATH, NEWS_PATH, ...Object.values(INFO_PATHS)])

export function customerNotificationTarget(item) {
  const id = typeof item.ReferenceId === 'string' && UUID.test(item.ReferenceId) ? item.ReferenceId : null
  if (Object.hasOwn(RESOURCES, item.ReferenceType)) {
    if (!id) return null
    const [path, title] = RESOURCES[item.ReferenceType]
    return { kind: 'detail', type: item.ReferenceType, id, path: path + id, title }
  }
  if (item.ReferenceType === 'Conversation') return id ? { kind: 'link', to: `${CHAT_PATH}?conversation=${id}` } : null
  const to = safeNext(item.ActionUrl, 'customer')
  if (!to) return null
  const path = new URL(to, 'https://vietech.invalid').pathname.replace(/\/$/, '') || '/'
  return PAGES.has(path) || /^\/(san-pham|danh-muc|thuong-hieu|tin-tuc)\/[^/]+$/.test(path) ? { kind: 'link', to } : null
}

export function notificationStatus(value) {
  return formatStatus(value, { Pending: 'Đang chờ', New: 'Mới', Confirmed: 'Đã xác nhận', Processing: 'Đang xử lý', Shipping: 'Đang giao',
    Delivered: 'Đã giao', Completed: 'Hoàn tất', Cancelled: 'Đã hủy', Paid: 'Đã thanh toán', Refunded: 'Đã hoàn tiền',
    Failed: 'Thất bại', Approved: 'Đã tiếp nhận', Receiving: 'Đang tiếp nhận', Inspecting: 'Đang kiểm tra',
    HandedOver: 'Đã bàn giao bảo hành', Rejected: 'Đã từ chối', Eligible: 'Đủ điều kiện', Ineligible: 'Không đủ điều kiện',
    Repaired: 'Đã sửa chữa', ProductReplaced: 'Đổi máy', PartReplaced: 'Thay linh kiện', NotRepairable: 'Không thể sửa chữa',
  })
}
