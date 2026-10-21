import { REVIEWABLE_ORDER_STATUSES } from '../../../lib/review-api.js'

// Order history in the customer account: the status tabs, the filters kept in the URL and the GET /orders query they
// make (docs/api-endpoints.md, "Lịch sử mua hàng"). Tabs group the API's OrderStatus values the way the customer sees
// them, so one tab may ask for several statuses (order_status repeats).

export const ORDER_HISTORY_PAGE_SIZE = 10

export const ORDER_TABS = [
  { id: '', label: 'Tất cả', statuses: [] },
  { id: 'pending', label: 'Chờ xác nhận', statuses: ['Pending'] },
  { id: 'processing', label: 'Đang xử lý', statuses: ['Confirmed', 'Processing'] },
  { id: 'shipping', label: 'Đang vận chuyển', statuses: ['Shipping'] },
  { id: 'received', label: 'Đã nhận hàng', statuses: ['Delivered', 'Completed'] },
  { id: 'cancelled', label: 'Đã hủy', statuses: ['Cancelled'] },
]

const DAY = /^\d{4}-\d{2}-\d{2}$/

// The filters in the URL (status, code, from, to, page); unknown or malformed values mean "no filter".
export function historyFilters(params) {
  const day = (key) => (DAY.test(params.get(key) ?? '') ? params.get(key) : '')
  const page = Number.parseInt(params.get('page') ?? '', 10)
  return {
    tab: ORDER_TABS.find((item) => item.id === params.get('status'))?.id ?? '',
    code: (params.get('code') ?? '').trim(),
    from: day('from'),
    to: day('to'),
    page: page > 0 ? page : 1,
  }
}

// Calendar days are Vietnam days: "from" starts at its 00:00 (+07:00) and "to" includes the whole day, as the API's
// range is half-open [ordered_from, ordered_to).
function vietnamMidnight(day) {
  return `${day}T00:00:00+07:00`
}

function dayAfter(day) {
  const [year, month, date] = day.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, date + 1)).toISOString().slice(0, 10)
}

export function historyQuery({ tab, code, from, to, page }) {
  return {
    order_status: ORDER_TABS.find((item) => item.id === tab)?.statuses ?? [],
    order_code: code,
    ordered_from: from ? vietnamMidnight(from) : undefined,
    ordered_to: to ? vietnamMidnight(dayAfter(to)) : undefined,
    page,
    page_size: ORDER_HISTORY_PAGE_SIZE,
  }
}

// "iPhone 18 Pro Max", or "iPhone 18 Pro Max và 2 sản phẩm khác" when the order has more lines.
export function orderItemsText(items = []) {
  if (!items.length) return ''
  const others = items.length - 1
  return others ? `${items[0].ProductName} và ${others} sản phẩm khác` : items[0].ProductName
}

// The products of a received order still to review on their product page (lines without a ReviewId), once each.
export function reviewProducts(order) {
  if (!REVIEWABLE_ORDER_STATUSES.includes(order.OrderStatus)) return []
  const names = new Map()
  for (const item of order.Items ?? []) {
    if (item.ProductSlug && !item.ReviewId && !names.has(item.ProductSlug)) names.set(item.ProductSlug, item.ProductName)
  }
  return [...names].map(([slug, name]) => ({ slug, name }))
}
