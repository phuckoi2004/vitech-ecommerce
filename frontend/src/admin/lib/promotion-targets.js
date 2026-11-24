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

export function promotionSelectedFamily(categoryIds, categories) {
  return [...new Set(categoryIds.flatMap((id) => promotionCategoryFamily(id, categories)))]
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
  const initial = { categoryIds: [], allProducts: true, productIds: [], changed: false }
  if (!row) return initial
  if (!productIds.length && !categoryIds.length) return { ...initial, categoryIds: [ALL_PROMOTION_CATEGORIES] }
  if (!productIds.length) {
    const top = promotionTopCategories(categoryIds, categories)
    if (categoryIds.length === 1 || sameSet(categoryIds, promotionSelectedFamily(top, categories))) return { ...initial, categoryIds: top }
  }
  if (productIds.length && !categoryIds.length) {
    const selected = productIds.map((id) => products.find((product) => product.ProductId === id))
    if (selected.every((product) => product && promotionProductCategory(product))) return {
      ...initial, categoryIds: [...new Set(selected.map(promotionProductCategory))], allProducts: false, productIds,
    }
  }
  // Preserve mixed or incomplete legacy scopes until the user explicitly replaces them.
  return { ...initial, categoryIds: [SAVED_PROMOTION_SCOPE] }
}

export function promotionTargetBody(selection, products, categories, original) {
  if (original && !selection.changed) return { ProductIds: (original.Products ?? []).map((item) => item.ProductId), CategoryIds: (original.Categories ?? []).map((item) => item.CategoryId) }
  if (selection.categoryIds.includes(ALL_PROMOTION_CATEGORIES)) return { ProductIds: [], CategoryIds: [] }
  if (!selection.categoryIds.length || selection.categoryIds.some((id) => !categories.some((category) => category.CategoryId === id))) throw new Error('Vui lòng chọn danh mục áp dụng.')
  const family = promotionSelectedFamily(selection.categoryIds, categories)
  if (selection.allProducts) return { ProductIds: [], CategoryIds: family }
  const ids = [...new Set(selection.productIds)]
  if (!ids.length) throw new Error('Vui lòng chọn ít nhất một sản phẩm hoặc chọn Tất cả sản phẩm.')
  if (ids.some((id) => !products.some((product) => product.ProductId === id && family.includes(promotionProductCategory(product))))) throw new Error('Sản phẩm đã chọn không thuộc danh mục hiện tại. Vui lòng chọn lại.')
  // The backend combines category/product targets with OR. For a subset, send product IDs only;
  // sending the category as well would unintentionally discount every product in that category.
  return { ProductIds: ids, CategoryIds: [] }
}
