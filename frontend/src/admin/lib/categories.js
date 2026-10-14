export const CATEGORY_PAGE_SIZE = 8

export function categoryFilter(params) {
  const page = Number(params.get('page'))
  return {
    keyword: params.get('keyword')?.trim() ?? '',
    status: ['active', 'hidden'].includes(params.get('status')) ? params.get('status') : '',
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  }
}

// Parent choices cannot point to the category itself or any of its descendants.
export function availableParents(categories, categoryId) {
  const excluded = new Set(categoryId ? [categoryId] : [])
  let changed = true
  while (changed) {
    changed = false
    for (const category of categories) {
      if (excluded.has(category.ParentCategoryId) && !excluded.has(category.CategoryId)) {
        excluded.add(category.CategoryId)
        changed = true
      }
    }
  }
  return categories.filter((category) => !excluded.has(category.CategoryId))
}
