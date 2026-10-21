// Upper limits end one cent before the next range, matching numeric(15, 2) prices.
export const PRICE_RANGES = [
  { value: 'under-5', label: 'Dưới 5 triệu', maxPrice: '4999999.99' },
  { value: '5-10', label: '5 – 10 triệu', minPrice: '5000000', maxPrice: '9999999.99' },
  { value: '10-15', label: '10 – 15 triệu', minPrice: '10000000', maxPrice: '14999999.99' },
  { value: '15-20', label: '15 – 20 triệu', minPrice: '15000000', maxPrice: '19999999.99' },
  { value: 'from-20', label: 'Từ 20 triệu', minPrice: '20000000' },
]

// "Sắp xếp theo" on the category page (Figma "Danh sách sản phẩm"); the first one is the default.
export const LISTING_SORTS = [
  { value: 'popular', label: 'Phổ biến' },
  { value: 'newest', label: 'Mới nhất' },
  { value: 'price_asc', label: 'Giá thấp đến cao' },
  { value: 'price_desc', label: 'Giá cao đến thấp' },
  { value: 'discount', label: 'Khuyến mãi tốt' },
  { value: 'best_selling', label: 'Bán chạy' },
]

// The category page keeps its filters in the URL: ?brand=<BrandId>&price=<range>&sort=<sort>&stock=1&new=1
// and one spec=<Key>:<Value> per chosen criterion option.
export function readListing(params) {
  const sort = LISTING_SORTS.find((item) => item.value === params.get('sort'))?.value ?? LISTING_SORTS[0].value
  return {
    brandId: params.get('brand') ?? '',
    price: params.get('price') ?? '',
    sort,
    inStock: params.get('stock') === '1',
    newArrivals: params.get('new') === '1',
    specs: [...new Set(params.getAll('spec').filter((spec) => /^[^:]+:.+$/.test(spec)))],
  }
}

export function hasListingFilters(listing) {
  return Boolean(listing.brandId || listing.price || listing.inStock || listing.newArrivals || listing.specs.length)
}

// A category's own ranges (GET /categories/{id}/filters), else the homepage menu's ranges its links use.
export function findPriceRange(value, ranges = []) {
  if (!value) return null
  const own = ranges.find((range) => range.Value === value)
  if (own) return { value: own.Value, label: own.Label, minPrice: own.MinPrice ?? undefined, maxPrice: own.MaxPrice ?? undefined }
  return PRICE_RANGES.find((range) => range.value === value) ?? null
}

// Only options the category still offers are sent, so an old link never turns into a failed request.
export function knownSpecs(specs, facets = []) {
  return specs.filter((spec) => {
    const [key, value] = [spec.slice(0, spec.indexOf(':')), spec.slice(spec.indexOf(':') + 1)]
    return facets.some((facet) => facet.Key === key && facet.Options.some((option) => option.Value === value))
  })
}

const letters = (text) => String(text ?? '').normalize('NFC').toLocaleLowerCase('vi-VN')
const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// News that mentions one of the terms as a whole word or phrase ("Loa" does not match "loại").
export function newsAbout(articles, terms) {
  const patterns = terms.filter(Boolean).map((term) => new RegExp(`(^|[^\\p{L}\\p{N}])${escape(letters(term))}($|[^\\p{L}\\p{N}])`, 'u'))
  return articles.filter((article) => patterns.some((pattern) => pattern.test(letters(`${article.Title} ${article.Summary ?? ''}`))))
}
