export const COUPON_PAGE_SIZE = 6
export const COUPON_VALIDITIES = { current: 'Còn hạn', upcoming: 'Sắp tới', expired: 'Hết hạn', inactive: 'Chưa bật' }
export const COUPON_STATUSES = { active: 'Đang áp dụng', upcoming: 'Chưa bắt đầu', exhausted: 'Hết lượt', expired: 'Hết chương trình' }
const searchKey = (value) => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLocaleLowerCase('vi')

export function couponFilters(params) {
  const page = Number(params.get('page'))
  const status = params.get('status')
  return { keyword: (params.get('keyword') ?? '').slice(0, 255), promotion: params.get('promotion') ?? '', type: ['Percentage', 'FixedAmount'].includes(params.get('type')) ? params.get('type') : '', validity: Object.hasOwn(COUPON_VALIDITIES, params.get('validity')) ? params.get('validity') : '', status: Object.hasOwn(COUPON_STATUSES, status) ? status : '', page: Number.isSafeInteger(page) && page > 0 ? page : 1 }
}
export function couponValidity(promotion, now = Date.now()) {
  const start = new Date(promotion.StartDate).getTime(), end = new Date(promotion.EndDate).getTime()
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 'inactive'
  if (now > end || promotion.Status === 'Expired') return 'expired'
  if (!['Active', 'Scheduled'].includes(promotion.Status)) return 'inactive'
  if (now < start) return 'upcoming'
  return 'current'
}
export function couponStatus(row, promotion = row?.Promotion, now = Date.now()) {
  // Persisted rows use the backend's status and clock. Derivation is only a form preview/legacy fallback.
  const serverStatus = { Active: 'active', Upcoming: 'upcoming', Exhausted: 'exhausted', Ended: 'expired' }[row?.Status]
  if (serverStatus) return serverStatus
  if (['Expired', 'Cancelled'].includes(promotion?.Status) || (promotion?.EndDate && now > new Date(promotion.EndDate).getTime())) return 'expired'
  if (row?.UsageLimit != null && row.UsedCount >= row.UsageLimit) return 'exhausted'
  return promotion && couponValidity(promotion, now) === 'current' ? 'active' : 'upcoming'
}
export const filterCoupons = (rows, filter, now = Date.now()) => rows.filter((row) => searchKey([row.Code, row.Name].join(' ')).includes(searchKey(filter.keyword.trim())) && (!filter.promotion || row.PromotionId === filter.promotion) && (!filter.type || row.Promotion.DiscountType === filter.type) && (!filter.validity || couponValidity(row.Promotion, row.EvaluatedAt ? Date.parse(row.EvaluatedAt) : now) === filter.validity) && (!filter.status || couponStatus(row, row.Promotion, now) === filter.status))
export const couponUsage = (row) => row.UsedCount + '/' + (row.UsageLimit ?? '∞')

export function couponForm(row, promotionId = '') {
  return { Code: row?.Code ?? '', Name: row?.Name ?? '', PromotionId: row?.PromotionId ?? promotionId, UsageLimit: row?.UsageLimit == null ? '' : String(row.UsageLimit) }
}
export function couponBody(form, usedCount = 0) {
  const Code = form.Code.trim(), Name = form.Name.trim(), limit = String(form.UsageLimit).trim()
  if (!Code || Code.length > 50) throw new Error('Mã giảm giá cần từ 1 đến 50 ký tự.')
  if (!Name || Name.length > 255) throw new Error('Tên mã giảm giá cần từ 1 đến 255 ký tự.')
  if (!form.PromotionId) throw new Error('Vui lòng chọn chương trình khuyến mãi.')
  if (limit && (!/^\d+$/.test(limit) || !Number.isSafeInteger(Number(limit)) || Number(limit) > 2147483647)) throw new Error('Giới hạn lượt dùng phải là số nguyên từ 0 đến 2.147.483.647.')
  const UsageLimit = limit ? Number(limit) : null
  if (UsageLimit !== null && UsageLimit < usedCount) throw new Error('Giới hạn lượt dùng không được nhỏ hơn số lượt đã dùng (' + usedCount + ').')
  return { Code, Name, PromotionId: form.PromotionId, UsageLimit }
}
export function couponPatch(form, row) {
  const body = couponBody(form, row.UsedCount)
  return Object.fromEntries(Object.entries(body).filter(([key, value]) => value !== row[key]))
}
export function couponError(error) {
  if (error.code === 'coupon_code_exists') return 'Mã giảm giá đã tồn tại. Mã không phân biệt chữ hoa và chữ thường.'
  if (error.code === 'coupon_in_use') return 'Mã đã được đơn hàng sử dụng nên không thể xóa.'
  return error.message
}
