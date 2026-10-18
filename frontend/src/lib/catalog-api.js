import { request } from '../services/api/client.js'
import { variantImages } from './product-detail.js'

// Public catalog and content endpoints (docs/api-endpoints.md). Called without a token, so the backend returns
// only what customers may see: active categories/brands, products on sale, published news, banners in their window.

export function listCategories({ parentId, rootsOnly = false, signal } = {}) {
  return request('/categories', { query: { parent_id: parentId, roots_only: rootsOnly || undefined }, signal })
}

export function listBrands({ signal } = {}) {
  return request('/brands', { signal })
}

// PageResponse[ProductSummary], newest first.
export function searchProducts({ keyword, categoryId, brandId, includeDescendants = false, minPrice, maxPrice, page = 1, pageSize = 20, signal } = {}) {
  return request('/products', {
    query: { keyword, category_id: categoryId, brand_id: brandId, include_descendants: includeDescendants || undefined, min_price: minPrice, max_price: maxPrice, page, page_size: pageSize },
    signal,
  })
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

export function listBanners({ signal } = {}) {
  return request('/banners', { signal })
}

export function listNews({ page = 1, pageSize = 3, signal } = {}) {
  return request('/news', { query: { page, page_size: pageSize }, signal })
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
  const prices = (product.Variants ?? []).map((variant) => Number(variant.Price)).filter(Number.isFinite)
  const images = variantImages(product, product.DefaultVariantId)
  return {
    id: product.ProductId,
    name: product.Name,
    slug: product.Slug,
    brandId: product.BrandId,
    price: prices.length ? Math.min(...prices) : null,
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
