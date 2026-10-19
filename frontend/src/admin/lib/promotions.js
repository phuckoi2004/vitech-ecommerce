export const PROMOTION_PAGE_SIZE = 6
export const PROMOTION_TYPES = { Percentage: 'Phần trăm', FixedAmount: 'Số tiền' }
export const PROMOTION_STATUSES = { Draft: 'Bản nháp', Scheduled: 'Sắp diễn ra', Active: 'Đang diễn ra', Expired: 'Đã kết thúc', Cancelled: 'Đã hủy' }
export const promotionMoney = (value) => Number(value).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + 'đ'
export const promotionValue = (row) => row.DiscountType === 'Percentage' ? Number(row.DiscountValue).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + '%' : promotionMoney(row.DiscountValue)
export const promotionDate = (value) => new Date(value).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })
export const promotionPeriod = (row) => promotionDate(row.StartDate) + ' – ' + promotionDate(row.EndDate)
export const promotionDateTime = (value) => promotionDate(value) + ' ' + localPromotionTime(value).slice(11, 16)
export function promotionTargetName(ids, rows, key) {
  return ids.map((id) => rows.find((row) => row[key] === id)?.Name ?? 'Đã chọn — không còn trong danh sách hiện tại').join(', ')
}
const fold = (value) => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLocaleLowerCase('vi')
export function promotionFilters(params) {
  const page = Number(params.get('page'))
  return { keyword: (params.get('keyword') ?? '').slice(0, 255), type: Object.hasOwn(PROMOTION_TYPES, params.get('type')) ? params.get('type') : '', status: Object.hasOwn(PROMOTION_STATUSES, params.get('status')) ? params.get('status') : '', page: Number.isSafeInteger(page) && page > 0 ? page : 1 }
}
export const filterPromotions = (rows, filter) => rows.filter((row) => fold(row.Name).includes(fold(filter.keyword.trim())) && (!filter.type || row.DiscountType === filter.type) && (!filter.status || row.Status === filter.status))
export function localPromotionTime(value) {
  if (!value) return ''
  const date = new Date(value), pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}
export function promotionForm(row) {
  return { Name: row?.Name ?? '', Description: row?.Description ?? '', DiscountType: row?.DiscountType ?? 'Percentage', DiscountValue: row?.DiscountValue ?? '', MinOrderValue: row?.MinOrderValue ?? '0', MaxDiscountAmount: row?.MaxDiscountAmount ?? '', StartDate: localPromotionTime(row?.StartDate), EndDate: localPromotionTime(row?.EndDate), Status: row?.Status ?? 'Draft', ProductIds: (row?.Products ?? []).map((item) => item.ProductId), CategoryIds: (row?.Categories ?? []).map((item) => item.CategoryId) }
}
export function promotionBody(form) {
  const Name = form.Name.trim()
  if (!Name || Name.length > 255) throw new Error('Tên chương trình cần từ 1 đến 255 ký tự.')
  if (!Object.hasOwn(PROMOTION_TYPES, form.DiscountType) || !Object.hasOwn(PROMOTION_STATUSES, form.Status)) throw new Error('Loại giảm hoặc trạng thái không hợp lệ.')
  const body = { Name, Description: form.Description.trim() || null, DiscountType: form.DiscountType, Status: form.Status }
  for (const key of ['DiscountValue', 'MinOrderValue', 'MaxDiscountAmount']) {
    const value = String(form[key]).trim()
    if (key === 'MaxDiscountAmount' && !value) { body[key] = null; continue }
    if (!/^\d{1,13}(\.\d{1,2})?$/.test(value)) throw new Error('Giá trị giảm và số tiền phải không âm, tối đa 13 chữ số và 2 chữ số thập phân.')
    body[key] = value
  }
  if (form.DiscountType === 'Percentage' && Number(body.DiscountValue) > 100) throw new Error('Giảm theo phần trăm không được vượt quá 100%.')
  if (!form.StartDate || !form.EndDate || !Number.isFinite(new Date(form.StartDate).getTime()) || !Number.isFinite(new Date(form.EndDate).getTime())) throw new Error('Vui lòng nhập thời gian bắt đầu và kết thúc hợp lệ.')
  body.StartDate = new Date(form.StartDate).toISOString(); body.EndDate = new Date(form.EndDate).toISOString()
  if (body.EndDate < body.StartDate) throw new Error('Thời gian kết thúc không được trước thời gian bắt đầu.')
  return { ...body, ProductIds: [...new Set(form.ProductIds)], CategoryIds: [...new Set(form.CategoryIds)] }
}
export function samePromotionTargets(left, right) {
  const expected = new Set(right)
  return left.length === right.length && left.every((id) => expected.has(id))
}
export function promotionPatch(form, original) {
  const next = promotionBody(form), before = promotionForm(original), patch = {}
  for (const key of ['Name', 'Description', 'Status', 'DiscountType', 'DiscountValue', 'MinOrderValue', 'MaxDiscountAmount', 'StartDate', 'EndDate']) {
    if (original.Status === 'Active' && !['Name', 'Description', 'Status'].includes(key)) continue
    if (['StartDate', 'EndDate'].includes(key) ? form[key] !== before[key] : String(next[key] ?? '') !== String(original[key] ?? '')) patch[key] = next[key]
  }
  return patch
}
