export const ALL_PROMOTION_CATEGORIES = '__all__'
export const SAVED_PROMOTION_SCOPE = '__saved__'
export const promotionProductCategory = (product) => product.CategoryId ?? product.Category?.CategoryId

export function initialPromotionTargets(row, products) {
  const productIds = (row?.Products ?? []).map((item) => item.ProductId), categoryIds = (row?.Categories ?? []).map((item) => item.CategoryId)
  const initial = { categoryId: '', allProducts: true, productIds: [], changed: false }
  if (!row) return initial
  if (!productIds.length && !categoryIds.length) return { ...initial, categoryId: ALL_PROMOTION_CATEGORIES }
  if (!productIds.length && categoryIds.length === 1) return { ...initial, categoryId: categoryIds[0] }
  if (productIds.length && !categoryIds.length) {
    const selected = productIds.map((id) => products.find((product) => product.ProductId === id))
    const categoryId = selected[0] && promotionProductCategory(selected[0])
    if (categoryId && selected.every((product) => product && promotionProductCategory(product) === categoryId)) return { ...initial, categoryId, allProducts: false, productIds }
  }
  // Existing mixed/multiple-category targets cannot be represented by a single category.
  // Preserve them until the user explicitly chooses a new category instead of silently broadening the scope.
  return { ...initial, categoryId: SAVED_PROMOTION_SCOPE }
}

export function promotionTargetBody(selection, products, categories, original) {
  if (original && !selection.changed) return { ProductIds: (original.Products ?? []).map((item) => item.ProductId), CategoryIds: (original.Categories ?? []).map((item) => item.CategoryId) }
  if (selection.categoryId === ALL_PROMOTION_CATEGORIES) return { ProductIds: [], CategoryIds: [] }
  if (!categories.some((category) => category.CategoryId === selection.categoryId)) throw new Error('Vui lòng chọn danh mục áp dụng.')
  if (selection.allProducts) return { ProductIds: [], CategoryIds: [selection.categoryId] }
  const ids = [...new Set(selection.productIds)]
  if (!ids.length) throw new Error('Vui lòng chọn ít nhất một sản phẩm hoặc chọn Tất cả sản phẩm.')
  if (ids.some((id) => !products.some((product) => product.ProductId === id && promotionProductCategory(product) === selection.categoryId))) throw new Error('Sản phẩm đã chọn không thuộc danh mục hiện tại. Vui lòng chọn lại.')
  // The backend combines category/product targets with OR. For a subset, send product IDs only;
  // sending the category as well would unintentionally discount every product in that category.
  return { ProductIds: ids, CategoryIds: [] }
}
