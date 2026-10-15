import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'
import { purchaseReadBatch } from './purchases.js'

const PATH = '/admin/news'
const articlePath = (id) => PATH + '/' + encodeURIComponent(id)

// The existing endpoint has status/page filters only. Read all pages before searching title/slug.
export async function getNewsDirectory(token, signal) {
  const first = await getAdminData(token, PATH, { page: 1, page_size: 100 }, signal)
  signal?.throwIfAborted()
  const pages = Array.from({ length: Math.max(0, Math.ceil(first.Total / 100) - 1) }, (_, index) => index + 2)
  const rest = await purchaseReadBatch(pages, (page) => getAdminData(token, PATH, { page, page_size: 100 }, signal), signal)
  return [...new Map([...first.Items, ...rest.flatMap((page) => page.Items)].map((article) => [article.NewsArticleId, article])).values()]
}

export const createNews = (accessToken, body) => request(PATH, { method: 'POST', accessToken, body })
export const updateNews = (accessToken, id, body) => request(articlePath(id), { method: 'PATCH', accessToken, body })
export const deleteNews = (accessToken, id) => request(articlePath(id), { method: 'DELETE', accessToken })
export const publishNews = (accessToken, id) => request(articlePath(id) + '/publish', { method: 'POST', accessToken })
export const hideNews = (accessToken, id) => request(articlePath(id) + '/hide', { method: 'POST', accessToken })
