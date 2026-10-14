export const ORDER_PAGE_SIZE = 5

export const ORDER_STATUSES = [
  ['', 'Tất cả', 'w-20'],
  ['Pending', 'Chờ xác nhận', 'w-[122px]'],
  ['Confirmed', 'Đã xác nhận', 'w-[112px]'],
  ['Processing', 'Đang xử lý', 'w-[112px]'],
  ['Shipping', 'Đang giao', 'w-[102px]'],
  ['Delivered', 'Đã giao', 'w-[90px]'],
  ['Completed', 'Hoàn tất', 'w-[88px]'],
  ['Cancelled', 'Đã hủy', 'w-[88px]'],
]

export const ORDER_NEXT = {
  Pending: ['Confirmed', 'Xác nhận đơn'],
  Confirmed: ['Processing', 'Bắt đầu xử lý'],
  Processing: ['Shipping', 'Chuyển đang giao'],
  Shipping: ['Delivered', 'Xác nhận đã giao'],
  Delivered: ['Completed', 'Hoàn tất'],
}

export const PAYMENT_LABELS = { Pending: 'Chưa thanh toán', Paid: 'Đã thanh toán', Failed: 'Thanh toán thất bại', Refunded: 'Đã hoàn tiền', Cancelled: 'Đã hủy thanh toán' }

export function orderFilters(params) {
  const rawPage = Number(params.get('page'))
  const status = params.get('status') ?? ''
  return {
    keyword: (params.get('keyword') ?? '').trim().slice(0, 255),
    status: ORDER_STATUSES.some(([value]) => value === status) ? status : '',
    page: Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1,
  }
}

export const orderStatusLabel = (value) => ORDER_STATUSES.find(([status]) => status === value)?.[1] ?? value
export const canCancelOrder = (order) => ['Pending', 'Confirmed', 'Processing', 'Shipping'].includes(order.OrderStatus)

// Preserve only list filters in detail/back links; a direct link never supplies an external redirect.
export function orderListSearch(params) {
  const search = new URLSearchParams()
  for (const key of ['keyword', 'status', 'page']) if (params.get(key)) search.set(key, params.get(key))
  return search.size ? '?' + search.toString() : ''
}

export function parseSerialNumbers(value) {
  const numbers = value.split(/[\n,;]+/).map((number) => number.trim()).filter(Boolean)
  if (!numbers.length) throw new Error('Vui lòng nhập Serial/IMEI thực tế của sản phẩm.')
  if (new Set(numbers.map((number) => number.toUpperCase())).size !== numbers.length) throw new Error('Danh sách Serial/IMEI bị trùng.')
  return numbers
}
