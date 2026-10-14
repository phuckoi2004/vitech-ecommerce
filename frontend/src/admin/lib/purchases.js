import { formatDate } from '../../lib/format.js'

export const PURCHASE_PAGE_SIZE = 5
export const PURCHASE_TABS = [['', 'Tất cả'], ['Pending', 'Chờ xác nhận'], ['Approved', 'Đã xác nhận'], ['Rejected', 'Từ chối'], ['history', 'Lịch sử đã xử lý']]
export const PURCHASE_STATUSES = { Pending: 'Chờ xác nhận', Approved: 'Đã xác nhận', Rejected: 'Từ chối', Receiving: 'Đang nhận hàng', Completed: 'Đã nhận đủ', Cancelled: 'Đã hủy', Closed: 'Đóng phiếu thiếu' }
export const purchaseEditable = (po) => ['Pending', 'Rejected'].includes(po.Status)
export const purchaseCancellable = (po) => ['Pending', 'Rejected', 'Approved'].includes(po.Status) && !po.Items?.some((item) => item.ReceivedQuantity > 0)
export const purchaseReceivable = (po) => ['Approved', 'Receiving'].includes(po.Status)
export const purchaseQuantity = (po) => po.Items.reduce((total, item) => total + item.OrderedQuantity, 0)
export const variantLabel = (variant) => [variant.Name, variant.VariantName, variant.Sku].filter(Boolean).join(' / ')

// Keep the list's filters when visiting a detail; dialog state belongs to its own page.
export function purchaseListSearch(params) {
  const next = new URLSearchParams()
  for (const key of ['keyword', 'status', 'supplier', 'product', 'from', 'to', 'page']) if (params.get(key)) next.set(key, params.get(key))
  return next.size ? '?' + next.toString() : ''
}

export function purchaseFilters(params) {
  const page = Number(params.get('page'))
  return {
    keyword: (params.get('keyword') ?? '').trim().slice(0, 255),
    status: PURCHASE_TABS.some(([value]) => value === params.get('status')) ? params.get('status') : '',
    supplier: params.get('supplier') ?? '', product: params.get('product') ?? '',
    from: validDate(params.get('from')) ? params.get('from') : '', to: validDate(params.get('to')) ? params.get('to') : '',
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  }
}
function validDate(value) { const date = new Date(value + 'T00:00:00Z'); return /^\d{4}-\d{2}-\d{2}$/.test(value ?? '') && !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value }
function fold(value) { return String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLowerCase() }
export function filterPurchases(rows, filter, variants) {
  const byId = new Map(variants.map((item) => [item.ProductVariantId, item]))
  const term = fold(filter.keyword)
  return rows.filter((po) => {
    const day = formatDate(po.CreatedAt).split('/').reverse().join('-')
    return (!filter.status || (filter.status === 'history' ? po.Status !== 'Pending' : po.Status === filter.status))
      && (!filter.supplier || po.SupplierId === filter.supplier)
      && (!filter.from || day >= filter.from) && (!filter.to || day <= filter.to)
      && (!filter.product || po.Items.some((item) => byId.get(item.ProductVariantId)?.ProductId === filter.product))
      && (!term || fold(po.PurchaseOrderCode).includes(term) || po.Items.some((item) => fold(variantLabel(byId.get(item.ProductVariantId) ?? {})).includes(term)))
  })
}
export function purchaseLineBody(line) {
  const quantity = Number(line.OrderedQuantity)
  const price = String(line.UnitPrice).trim()
  if (!line.ProductVariantId) throw new Error('Vui lòng chọn biến thể sản phẩm.')
  if (!Number.isSafeInteger(quantity) || quantity <= 0 || quantity > 2147483647) throw new Error('Số lượng đặt phải là số nguyên dương hợp lệ.')
  if (!/^\d{1,13}(\.\d{1,2})?$/.test(price)) throw new Error('Đơn giá nhập phải không âm và tối đa 2 chữ số thập phân.')
  return { ProductVariantId: line.ProductVariantId, OrderedQuantity: quantity, UnitPrice: price, Note: line.Note?.trim() || null }
}
export function purchaseCreateBody(form) {
  if (!form.SupplierId) throw new Error('Vui lòng chọn nhà cung cấp đang hoạt động.')
  if (!form.Items.length) throw new Error('Phiếu nhập phải có ít nhất một sản phẩm.')
  const items = form.Items.map(purchaseLineBody)
  if (new Set(items.map((item) => item.ProductVariantId)).size !== items.length) throw new Error('Mỗi biến thể chỉ được xuất hiện một lần trong phiếu nhập.')
  return { SupplierId: form.SupplierId, Note: form.Note.trim() || null, Items: items }
}
export function purchaseReceiveBody(po, values, variants, note) {
  const byId = new Map(variants.map((variant) => [variant.ProductVariantId, variant]))
  const allSerials = new Set()
  const items = po.Items.flatMap((item) => {
    const value = values[item.PurchaseOrderItemId] ?? {}
    const quantity = Number(value.Quantity || 0)
    if (!quantity && !String(value.SerialNumbers ?? '').trim()) return []
    if (!Number.isInteger(quantity) || quantity <= 0 || quantity > item.OrderedQuantity - item.ReceivedQuantity) throw new Error('Số lượng nhận phải là số nguyên dương và không vượt số còn thiếu.')
    const variant = byId.get(item.ProductVariantId)
    if (!variant) throw new Error('Cần tải được thông tin biến thể trước khi nhận hàng.')
    const numbers = String(value.SerialNumbers ?? '').split(/[\n,;]+/).map((number) => number.trim()).filter(Boolean)
    if (variant.IsSerialTracked ? numbers.length !== quantity : numbers.length > 0) throw new Error(variant.IsSerialTracked ? 'Mỗi sản phẩm nhận cần đúng một Serial/IMEI thực tế.' : 'Biến thể này không quản lý Serial/IMEI.')
    for (const number of numbers) {
      if (number.length > 100 || allSerials.has(number)) throw new Error('Serial/IMEI bị trùng hoặc vượt quá 100 ký tự.')
      allSerials.add(number)
    }
    return [{ PurchaseOrderItemId: item.PurchaseOrderItemId, Quantity: quantity, SerialNumbers: numbers }]
  })
  if (!items.length) throw new Error('Vui lòng nhập ít nhất một sản phẩm thực nhận.')
  return { Items: items, Note: note.trim() || null }
}

export function purchaseCsv(rows, supplierNames, creatorNames) {
  const cell = (value) => '"' + String(value ?? '').replace(/^[\s]*[=+@-]/, (prefix) => "'" + prefix).replace(/"/g, '""') + '"'
  const data = [['Mã phiếu', 'Nhà cung cấp', 'Người tạo', 'Ngày lập', 'Tổng SL', 'Tổng tiền', 'Trạng thái'], ...rows.map((po) => [po.PurchaseOrderCode, supplierNames[po.SupplierId] ?? '', creatorNames[po.CreatedByUserId] ?? '', formatDate(po.CreatedAt), purchaseQuantity(po), po.TotalAmount, PURCHASE_STATUSES[po.Status] ?? po.Status])]
  return '\uFEFF' + data.map((row) => row.map(cell).join(',')).join('\r\n')
}
