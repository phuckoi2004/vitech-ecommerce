// Display labels only. Requests, filters and workflow comparisons keep API codes.
const STATUS_LABELS = {
  Pending: 'Chờ xử lý', New: 'Mới', Confirmed: 'Đã xác nhận', Processing: 'Đang xử lý',
  Shipping: 'Đang giao', Delivered: 'Đã giao', Completed: 'Hoàn tất', Cancelled: 'Đã hủy',
  Approved: 'Đã duyệt', Rejected: 'Đã từ chối', Receiving: 'Đang nhận hàng',
  Paid: 'Đã thanh toán', Success: 'Thành công', Failed: 'Thất bại', Refunded: 'Đã hoàn tiền',
  Draft: 'Bản nháp', Active: 'Đang hoạt động', Inactive: 'Tạm ẩn', Discontinued: 'Ngừng kinh doanh',
  Scheduled: 'Đã lên lịch', Expired: 'Hết hạn', Published: 'Đã đăng', Hidden: 'Đã ẩn', Locked: 'Đã khóa',
  Open: 'Đang mở', Closed: 'Đã đóng', Available: 'Có sẵn', Reserved: 'Đã giữ chỗ', Sold: 'Đã bán',
  Warranty: 'Đang bảo hành', Returned: 'Đã trả lại', WrittenOff: 'Đã xuất hủy',
  Eligible: 'Đủ điều kiện', Ineligible: 'Không đủ điều kiện', Inspecting: 'Đang kiểm tra',
  HandedOver: 'Đã bàn giao bảo hành', Repairing: 'Đang sửa chữa', Finished: 'Hoàn tất',
  Repaired: 'Đã sửa chữa', ProductReplaced: 'Đổi máy', PartReplaced: 'Thay linh kiện', NotRepairable: 'Không thể sửa chữa',
  Upcoming: 'Sắp bắt đầu', Exhausted: 'Hết lượt sử dụng', Ended: 'Đã kết thúc',
}

export function formatStatus(value, labels = {}) {
  if (value == null || value === '') return '—'
  if (Object.hasOwn(labels, value)) return labels[value]
  return Object.hasOwn(STATUS_LABELS, value) ? STATUS_LABELS[value] : 'Chưa xác định'
}
