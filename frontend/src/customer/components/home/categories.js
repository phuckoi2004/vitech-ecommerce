const nameKey = (value) => String(value ?? '').normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/gi, 'd').toLowerCase().replace(/[\s_]+/g, '-')

const aliases = {
  phone: ['dien-thoai', 'phone', 'smartphone'], laptop: ['laptop', 'may-tinh-xach-tay'],
  desktop: ['may-tinh-de-ban', 'pc', 'desktop'], components: ['linh-kien-may-tinh', 'linh-kien', 'components'],
  accessories: ['phu-kien', 'accessories'], smartHome: ['gia-dung-thong-minh', 'smart-home', 'gia-dung'],
}

// Prefer the design's groups only when those categories exist; the rest retain their API display order.
export function selectHomeCategories(categories, preferred, limit) {
  const selected = []
  for (const group of preferred) {
    const found = categories.find((item) => aliases[group].some((key) => key === nameKey(item.Slug) || key === nameKey(item.Name)))
    if (found && !selected.includes(found)) selected.push(found)
  }
  return [...selected, ...categories.filter((item) => !selected.includes(item))].slice(0, limit)
}
