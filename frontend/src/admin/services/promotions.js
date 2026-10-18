import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'
import { purchaseReadBatch } from './purchases.js'

const PATH = '/admin/promotions'
const promotionPath = (id) => PATH + '/' + encodeURIComponent(id)

// The API filters by status only. Fetch every page before searching or filtering by discount type.
async function readAll(token, path, key, signal) {
  const first = await getAdminData(token, path, { page: 1, page_size: 100 }, signal)
  signal?.throwIfAborted()
  const pages = Array.from({ length: Math.max(0, Math.ceil(first.Total / 100) - 1) }, (_, index) => index + 2)
  const rest = await purchaseReadBatch(pages, (page) => getAdminData(token, path, { page, page_size: 100 }, signal), signal)
  return [...new Map([...first.Items, ...rest.flatMap((page) => page.Items)].map((row) => [row[key], row])).values()]
}
export const getPromotionDirectory = (token, signal) => readAll(token, PATH, 'PromotionId', signal)
export const getPromotionProducts = (token, signal) => readAll(token, '/admin/products', 'ProductId', signal)
export const createPromotion = (token, body) => request(PATH, { method: 'POST', accessToken: token, body })
export const updatePromotion = (token, id, body) => request(promotionPath(id), { method: 'PATCH', accessToken: token, body })
export const updatePromotionTargets = (token, id, body) => request(promotionPath(id) + '/targets', { method: 'PUT', accessToken: token, body })
export const deletePromotion = (token, id) => request(promotionPath(id), { method: 'DELETE', accessToken: token })
export const cancelPromotion = (token, id) => request(promotionPath(id) + '/cancel', { method: 'POST', accessToken: token })
