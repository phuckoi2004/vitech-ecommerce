export const PRODUCT_STATUSES = [['Draft', 'Bản nháp'], ['Active', 'Đang bán'], ['Inactive', 'Tạm ẩn'], ['Discontinued', 'Ngừng kinh doanh']]
export const PRICE_RANGES = [
  ['under-5m', 'Dưới 5 triệu', undefined, '4999999.99'],
  ['5m-15m', '5 đến dưới 15 triệu', '5000000', '14999999.99'],
  ['15m-30m', '15 đến dưới 30 triệu', '15000000', '29999999.99'],
  ['over-30m', 'Từ 30 triệu', '30000000', undefined],
]
export const STOCK_FILTERS = [['in_stock', 'Còn hàng'], ['low_stock', 'Sắp hết'], ['out_of_stock', 'Hết hàng']]
export const PRODUCT_PAGE_SIZE = 8

export function productQuery(params) {
  const price = PRICE_RANGES.find(([key]) => key === params.get('price'))
  const rawPage = Number(params.get('page'))
  return {
    keyword: params.get('keyword')?.trim() || undefined,
    category_id: params.get('category_id') || undefined,
    brand_id: params.get('brand_id') || undefined,
    status: PRODUCT_STATUSES.some(([key]) => key === params.get('status')) ? params.get('status') : undefined,
    stock: STOCK_FILTERS.some(([key]) => key === params.get('stock')) ? params.get('stock') : undefined,
    min_price: price?.[2], max_price: price?.[3],
    page: Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1,
    page_size: PRODUCT_PAGE_SIZE,
  }
}

export function productStatus(product) {
  if (product.Status !== 'Active') return [PRODUCT_STATUSES.find(([key]) => key === product.Status)?.[1] ?? product.Status, 'bg-admin-soft text-admin-muted']
  if (product.IsActive === false) return ['Tạm ẩn', 'bg-admin-soft text-admin-muted']
  if (product.StockQuantity === 0) return ['Hết hàng', 'bg-admin-red/10 text-admin-red']
  if (product.IsLowStock) return ['Sắp hết', 'bg-amber-500/12 text-amber-600']
  return ['Đang bán', 'bg-green-600/10 text-green-600']
}

export function productInitials(name = '') {
  return name.trim().split(/\s+/).slice(0, 2).map((word) => word[0]).join('').toUpperCase() || 'SP'
}

export function slugFromName(name) {
  return name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}
