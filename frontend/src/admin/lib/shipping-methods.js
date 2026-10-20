export const SHIPPING_PAGE_SIZE = 5
export const SHIPPING_PAGE_TITLES = { new: 'Thêm phương thức vận chuyển', edit: 'Sửa phương thức vận chuyển' }
export const shippingDays = (days) => days === 0 ? 'Trong ngày' : `${days} ngày`

export function shippingFilters(params) {
  const page = Number(params.get('page')), days = params.get('days') ?? ''
  return { keyword: (params.get('keyword') ?? '').slice(0, 255),
    status: ['active', 'inactive'].includes(params.get('status')) ? params.get('status') : '',
    days: /^\d+$/.test(days) && Number(days) <= 30 ? days : '',
    page: Number.isSafeInteger(page) && page > 0 ? page : 1 }
}
const fold = (text) => String(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLowerCase()
export function filterShippingMethods(rows, filter) {
  const term = fold(filter.keyword.trim())
  return rows.filter((row) => (!term || fold(row.Code).includes(term) || fold(row.Name).includes(term))
    && (!filter.status || row.IsActive === (filter.status === 'active'))
    && (filter.days === '' || row.EstimatedDays === Number(filter.days)))
}
export function shippingListSearch(params) {
  const next = new URLSearchParams()
  for (const key of ['keyword', 'status', 'days', 'page']) if (params.get(key)) next.set(key, params.get(key))
  return next.size ? '?' + next.toString() : ''
}
export function shippingPagePath(mode, id, params) {
  return '/admin/shipping-methods/' + (mode === 'new' ? 'new' : encodeURIComponent(id) + '/edit') + shippingListSearch(params)
}
export function shippingBody(form) {
  const Code = form.Code.trim(), Name = form.Name.trim(), fee = String(form.BaseFee).trim(), days = String(form.EstimatedDays).trim()
  if (!Code || Code.length > 50) throw new Error('Mã phương thức cần từ 1 đến 50 ký tự.')
  if (!Name || Name.length > 255) throw new Error('Tên phương thức cần từ 1 đến 255 ký tự.')
  // VND nguyên đồng; "30000.00" đọc từ API vẫn hợp lệ (phần thập phân bằng 0).
  if (!/^\d{1,13}(\.0{1,2})?$/.test(fee)) throw new Error('Phí cơ bản phải là số nguyên VND không âm, tối đa 13 chữ số.')
  if (!/^\d+$/.test(days) || Number(days) > 30) throw new Error('Số ngày giao dự kiến phải là số nguyên từ 0 đến 30.')
  if (typeof form.IsActive !== 'boolean') throw new Error('Vui lòng chọn trạng thái hợp lệ.')
  return { Code, Name, BaseFee: fee, EstimatedDays: Number(days), IsActive: form.IsActive }
}
