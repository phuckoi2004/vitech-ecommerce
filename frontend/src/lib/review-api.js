import { request } from '../services/api/client.js'

export const REVIEW_PAGE_SIZE = 5
export const REVIEW_EDIT_WINDOW_MS = 7 * 24 * 60 * 60 * 1000

export function listProductReviews(productId, { rating, page = 1, pageSize = REVIEW_PAGE_SIZE, signal } = {}) {
  return request(`/products/${encodeURIComponent(productId)}/reviews`, {
    query: { rating, page, page_size: pageSize }, signal,
  })
}

// The API provides Total for each star filter. Count the whole result, rather than the current page.
export async function getProductReviewSummary(productId, { signal } = {}) {
  const distribution = await Promise.all([5, 4, 3, 2, 1].map(async (rating) => {
    const result = await listProductReviews(productId, { rating, pageSize: 1, signal })
    return { rating, count: result.Total }
  }))
  const count = distribution.reduce((sum, item) => sum + item.count, 0)
  const weighted = distribution.reduce((sum, item) => sum + item.rating * item.count, 0)
  // Match the backend's two-decimal average before formatting it for display.
  const rating = count ? Math.round((weighted / count + Number.EPSILON) * 100) / 100 : 0
  return { count, rating, distribution }
}

export function canEditReview(review, userId, now = Date.now()) {
  const createdAt = Date.parse(review.CreatedAt)
  return !!userId && review.User?.UserId === userId && !review.IsDeleted && Number.isFinite(createdAt)
    && now < createdAt + REVIEW_EDIT_WINDOW_MS
}

export function reviewableOrderItems(order, product) {
  if (order?.OrderStatus !== 'Delivered') return []
  // Include inactive variants too: a previous purchase remains reviewable when that variant stops selling.
  const variantIds = new Set((product.Variants ?? []).map((item) => item.ProductVariantId))
  return (order.Items ?? []).filter((item) => variantIds.has(item.ProductVariantId))
}
