import { request } from '../services/api/client.js'
import { variantImages, variantPrice } from './product-detail.js'

// Public catalog and content endpoints (docs/api-endpoints.md). Called without a token, so the backend returns
// only what customers may see: active categories/brands, products on sale, published news, banners in their window.

export function listCategories({ parentId, rootsOnly = false, signal } = {}) {
  return request('/categories', { query: { parent_id: parentId, roots_only: rootsOnly || undefined }, signal })
}

export function listBrands({ signal } = {}) {
  return request('/brands', { signal })
}

export function listCategoryOffers({ signal } = {}) {
  return request('/pricing/category-offers', { signal })
}

// PageResponse[ProductSummary]. Without `sort`: relevance for keyword searches, newest for browsing. `specs` are "<Key>:<Value>" options
// from getCategoryFilters and need a categoryId.
export function searchProducts({ keyword, categoryId, brandId, includeDescendants = false, minPrice, maxPrice, sort, inStock = false,
  newArrivals = false, specs, page = 1, pageSize = 20, signal } = {}) {
  return request('/products', {
    query: { keyword, category_id: categoryId, brand_id: brandId, include_descendants: includeDescendants || undefined, min_price: minPrice, max_price: maxPrice,
      sort, in_stock: inStock || undefined, new_arrivals: newArrivals || undefined, spec: specs, page, page_size: pageSize },
    signal,
  })
}

// What the box under the search field offers while typing: { Searches: [{ Label, CategorySlug, BrandId, ImageUrl }],
// Products: [{ ProductId, Name, Slug, ImageUrl, Price, OriginalPrice }] }, in one request.
export function getSearchSuggestions(keyword, { signal } = {}) {
  return request('/products/suggestions', { query: { keyword }, signal })
}

// Root categories and brands of what searchProducts finds with the same filters, with counts, most products first.
// Each group ignores its own filter; categoryId includes its children.
export function getSearchFilters({ keyword, categoryId, brandId, minPrice, maxPrice, inStock = false, signal } = {}) {
  return request('/products/filters', {
    query: { keyword, category_id: categoryId, brand_id: brandId, min_price: minPrice, max_price: maxPrice, in_stock: inStock || undefined },
    signal,
  })
}

// Brands, price ranges and specification criteria that have products on sale in the category and its children.
export function getCategoryFilters(categoryId, { signal } = {}) {
  return request(`/categories/${encodeURIComponent(categoryId)}/filters`, { signal })
}

// The existing backend lists summaries newest first. Read all summary pages only for comparisons that need
// the full set (best-selling or category-specific brands); product details are fetched only for visible cards.
export async function listProductSummaries({ signal, ...filters } = {}) {
  const pageSize = 100
  const first = await searchProducts({ ...filters, page: 1, pageSize, signal })
  const pages = Math.max(1, Math.ceil(Number(first.Total || 0) / pageSize))
  const items = [...first.Items]
  for (let page = 2; page <= pages; page++) {
    signal?.throwIfAborted()
    const next = await searchProducts({ ...filters, page, pageSize, signal })
    if (!next.Items.length) break
    items.push(...next.Items)
  }
  return [...new Map(items.map((item) => [item.ProductId, item])).values()]
}

export function getProduct(productId, { signal } = {}) {
  return request(`/products/${encodeURIComponent(productId)}`, { signal })
}

// With categoryId: only the banners for that product list page, its own first (see GET /banners).
export function listBanners({ categoryId, signal } = {}) {
  return request('/banners', { query: categoryId ? { category_id: categoryId } : undefined, signal })
}

export function listNews({ page = 1, pageSize = 3, signal } = {}) {
  return request('/news', { query: { page, page_size: pageSize }, signal })
}

// Public coupons still running with uses left: [{ CouponId, Code, Name, DiscountType, DiscountValue, MinOrderValue,
// MaxDiscountAmount, EndDate, RemainingUses }]. Only a suggestion: the cart's coupon preview decides if one applies.
export function listCoupons({ signal } = {}) {
  return request('/coupons', { signal })
}

export function listPaymentMethods({ signal } = {}) {
  return request('/payment-methods', { signal })
}

export function listShippingMethods({ signal } = {}) {
  return request('/shipping-methods', { signal })
}

// What a product card shows, from a ProductDetailResponse (its variants are the ones on sale). `price` is the
// lowest variant price (null without a sellable variant).
export function toProductCard(product) {
  const variants = (product.Variants ?? []).filter((variant) => variant.IsActive !== false && variantPrice(variant) !== null)
  const cheapest = variants.reduce((best, variant) => !best || variantPrice(variant) < variantPrice(best) ? variant : best, null)
  const sale = cheapest && variantPrice(cheapest)
  const original = cheapest && Number(cheapest.OriginalPrice ?? cheapest.Price)
  const images = variantImages(product, product.DefaultVariantId)
  return {
    id: product.ProductId,
    name: product.Name,
    slug: product.Slug,
    brandId: product.BrandId,
    price: cheapest ? sale : null,
    ...(cheapest && original > sale ? { originalPrice: original,
      discountPercent: Number(cheapest.DiscountPercent) || (original - sale) / original * 100 } : {}),
    imageUrl: images[0]?.ImageUrl ?? null,
    rating: Number(product.AverageRating) || 0,
    reviewCount: product.ReviewCount ?? 0,
    sold: product.SoldQuantity ?? 0,
    inStock: (product.Variants ?? []).some((variant) => variant.StockQuantity > 0),
  }
}

// The product list has no price or image (ProductSummary), so each card reads its product detail. A product
// that is no longer on sale by then (404) is omitted; service/network failures must remain retryable.
export async function loadProductCards(summaries, { signal } = {}) {
  const details = await Promise.all(summaries.map((item) => getProduct(item.ProductId, { signal }).catch((failure) => {
    if (signal?.aborted) throw failure
    if (failure.status === 404) return null
    throw failure
  })))
  return details.filter(Boolean).map(toProductCard)
}

export const getCategoryBySlug = (slug, { signal } = {}) => request(`/categories/slug/${encodeURIComponent(slug)}`, { signal })
export const getBrandBySlug = (slug, { signal } = {}) => request(`/brands/slug/${encodeURIComponent(slug)}`, { signal })
export const getProductBySlug = (slug, { signal } = {}) => request(`/products/slug/${encodeURIComponent(slug)}`, { signal })
export const getNews = (slug, { signal } = {}) => request(`/news/${encodeURIComponent(slug)}`, { signal })
export const recordNewsView = (slug) => request(`/news/${encodeURIComponent(slug)}/views`, { method: 'POST' })
