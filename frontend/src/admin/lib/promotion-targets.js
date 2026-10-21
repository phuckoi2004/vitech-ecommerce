export const ALL_PROMOTION_CATEGORIES = '__all__'
export const SAVED_PROMOTION_SCOPE = '__saved__'
export const promotionProductCategory = (product) => product.CategoryId ?? product.Category?.CategoryId

// Products sit in sub-categories ("Điện thoại pin trâu"), never directly in a root such as "Điện thoại", and the backend
// matches a category target exactly. Choosing a category therefore means that category and all of its descendants.
export function promotionCategoryFamily(categoryId, categories) {
  const family = [categoryId]
  for (let index = 0; index < family.length; index += 1) {
    for (const category of categories) if (category.ParentCategoryId === family[index] && !family.includes(category.CategoryId)) family.push(category.CategoryId)
  }
  return family
}

// Roots first, each followed by its children, for the category picker.
export function promotionCategoryOptions(categories) {
  const known = new Set(categories.map((category) => category.CategoryId)), result = []
  const visit = (parentId, depth) => {
    for (const category of categories) {
      const parent = known.has(category.ParentCategoryId) ? category.ParentCategoryId : null
      if (parent === parentId && !result.some((item) => item.category === category)) { result.push({ category, depth }); visit(category.CategoryId, depth + 1) }
    }
  }
  visit(null, 0)
  return result
}

// Saved category targets, without the descendants that were added along with a chosen parent.
export function promotionTopCategories(categoryIds, categories) {
  const ids = new Set(categoryIds)
  return categoryIds.filter((id) => !ids.has(categories.find((category) => category.CategoryId === id)?.ParentCategoryId))
}

const sameSet = (left, right) => left.length === right.length && left.every((id) => right.includes(id))

export function initialPromotionTargets(row, products, categories = []) {
  const productIds = (row?.Products ?? []).map((item) => item.ProductId), categoryIds = (row?.Categories ?? []).map((item) => item.CategoryId)
  const initial = { categoryId: '', allProducts: true, productIds: [], changed: false }
  if (!row) return initial
  if (!productIds.length && !categoryIds.length) return { ...initial, categoryId: ALL_PROMOTION_CATEGORIES }
  if (!productIds.length) {
    const top = promotionTopCategories(categoryIds, categories)
    if (categoryIds.length === 1) return { ...initial, categoryId: categoryIds[0] }
    if (top.length === 1 && sameSet(categoryIds, promotionCategoryFamily(top[0], categories))) return { ...initial, categoryId: top[0] }
  }
  if (productIds.length && !categoryIds.length) {
    const selected = productIds.map((id) => products.find((product) => product.ProductId === id))
    let categoryId = selected[0] && promotionProductCategory(selected[0])
    // The closest category that holds every selected product: their own category, or a parent of it.
    while (categoryId && selected.every(Boolean)) {
      const family = promotionCategoryFamily(categoryId, categories)
      if (selected.every((product) => family.includes(promotionProductCategory(product)))) return { ...initial, categoryId, allProducts: false, productIds }
      categoryId = categories.find((category) => category.CategoryId === categoryId)?.ParentCategoryId
    }
  }
  // Existing mixed/multiple-category targets cannot be represented by a single category.
  // Preserve them until the user explicitly chooses a new category instead of silently broadening the scope.
  return { ...initial, categoryId: SAVED_PROMOTION_SCOPE }
}

export function promotionTargetBody(selection, products, categories, original) {
  if (original && !selection.changed) return { ProductIds: (original.Products ?? []).map((item) => item.ProductId), CategoryIds: (original.Categories ?? []).map((item) => item.CategoryId) }
  if (selection.categoryId === ALL_PROMOTION_CATEGORIES) return { ProductIds: [], CategoryIds: [] }
  if (!categories.some((category) => category.CategoryId === selection.categoryId)) throw new Error('Vui lòng chọn danh mục áp dụng.')
  const family = promotionCategoryFamily(selection.categoryId, categories)
  if (selection.allProducts) return { ProductIds: [], CategoryIds: family }
  const ids = [...new Set(selection.productIds)]
  if (!ids.length) throw new Error('Vui lòng chọn ít nhất một sản phẩm hoặc chọn Tất cả sản phẩm.')
  if (ids.some((id) => !products.some((product) => product.ProductId === id && family.includes(promotionProductCategory(product))))) throw new Error('Sản phẩm đã chọn không thuộc danh mục hiện tại. Vui lòng chọn lại.')
  // The backend combines category/product targets with OR. For a subset, send product IDs only;
  // sending the category as well would unintentionally discount every product in that category.
  return { ProductIds: ids, CategoryIds: [] }
}
