import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'

async function readBatches(values, read, signal) {
  const output = []
  for (let index = 0; index < values.length; index += 4) {
    signal?.throwIfAborted()
    const results = await Promise.allSettled(values.slice(index, index + 4).map(read))
    signal?.throwIfAborted()
    // Let the session layer refresh/retry auth failures before reporting other read errors.
    const session = results.find((result) => result.status === 'rejected' && [401, 403].includes(result.reason.status))
    if (session) throw session.reason
    for (const result of results) { if (result.status === 'rejected') throw result.reason; output.push(result.value) }
  }
  return output
}

async function readPages(token, path, query, signal, key) {
  const first = await getAdminData(token, path, { ...query, page: 1, page_size: 100 }, signal)
  const numbers = Array.from({ length: Math.max(0, Math.ceil(first.Total / 100) - 1) }, (_, index) => index + 2)
  const rest = await readBatches(numbers, (page) => getAdminData(token, path, { ...query, page, page_size: 100 }, signal), signal)
  return [...new Map([...first.Items, ...rest.flatMap((page) => page.Items)].map((item) => [item[key], item])).values()]
}

// The existing admin API lists reviews per parent product. Load all product/review pages,
// including historical products, before applying global filters, counts and pagination.
export async function getReviewDirectory(token, signal) {
  const products = await readPages(token, '/admin/products', { include_deleted: true }, signal, 'ProductId')
  const groups = await readBatches(products, (product) => readPages(token, '/admin/products/' + encodeURIComponent(product.ProductId) + '/reviews', { include_deleted: true }, signal, 'ReviewId'), signal)
  const names = new Map(products.map((product) => [product.ProductId, product.Name]))
  return [...new Map(groups.flat().map((review) => [review.ReviewId, { ...review, ProductName: names.get(review.ProductId) ?? null }])).values()]
    .sort((left, right) => new Date(right.CreatedAt).getTime() - new Date(left.CreatedAt).getTime() || left.ReviewId.localeCompare(right.ReviewId))
}

export const hideReview = (token, id, reason) => request('/admin/reviews/' + encodeURIComponent(id) + '/hide', { method: 'POST', accessToken: token, body: { DeleteReason: reason.trim() || null } })
