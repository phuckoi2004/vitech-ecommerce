import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'

const PATH = '/admin/purchase-orders'
const poPath = (id) => PATH + '/' + encodeURIComponent(id)

export async function purchaseReadBatch(values, read, signal, optional = false) {
  const output = []
  for (let index = 0; index < values.length; index += 4) {
    signal?.throwIfAborted()
    const results = await Promise.allSettled(values.slice(index, index + 4).map(read))
    signal?.throwIfAborted()
    const session = results.find((result) => result.status === 'rejected' && [401, 403].includes(result.reason.status))
    if (session) throw session.reason
    for (const result of results) {
      if (result.status === 'rejected' && !optional) throw result.reason
      output.push(result.status === 'fulfilled' ? result.value : null)
    }
  }
  return output
}

export async function readPurchasePages(token, path, query = {}, signal) {
  const first = await getAdminData(token, path, { ...query, page: 1, page_size: 100 }, signal)
  signal?.throwIfAborted()
  const pages = Array.from({ length: Math.max(0, Math.ceil(first.Total / 100) - 1) }, (_, index) => index + 2)
  const rest = await purchaseReadBatch(pages, (page) => getAdminData(token, path, { ...query, page, page_size: 100 }, signal), signal)
  return [...new Map([...(first.Items ?? []), ...rest.flatMap((page) => page.Items)].map((row) => [row.PurchaseOrderId ?? row.ProductVariantId ?? row.SupplierId, row])).values()]
}

// Existing list DTOs omit line quantities and product/date filters, so filtering uses fully loaded details.
export async function getPurchaseDirectory(token, signal) {
  const summaries = await readPurchasePages(token, PATH, {}, signal)
  return purchaseReadBatch(summaries, (row) => getAdminData(token, poPath(row.PurchaseOrderId), {}, signal), signal)
}

export const getPurchaseVariants = (token, signal) => readPurchasePages(token, '/admin/variants', {}, signal)
export const createPurchase = (accessToken, body) => request(PATH, { method: 'POST', accessToken, body })
export const updatePurchase = (accessToken, id, body) => request(poPath(id), { method: 'PATCH', accessToken, body })
export const addPurchaseItem = (accessToken, id, body) => request(poPath(id) + '/items', { method: 'POST', accessToken, body })
export const updatePurchaseItem = (accessToken, id, itemId, body) => request(poPath(id) + '/items/' + encodeURIComponent(itemId), { method: 'PATCH', accessToken, body })
export const removePurchaseItem = (accessToken, id, itemId) => request(poPath(id) + '/items/' + encodeURIComponent(itemId), { method: 'DELETE', accessToken })
export const decidePurchase = (accessToken, id, body) => request(poPath(id) + '/decision', { method: 'POST', accessToken, body })
export const deletePurchase = (accessToken, id) => request(poPath(id), { method: 'DELETE', accessToken })
export const resubmitPurchase = (accessToken, id) => request(poPath(id) + '/resubmit', { method: 'POST', accessToken })
export const receivePurchase = (accessToken, id, body) => request(poPath(id) + '/receive', { method: 'POST', accessToken, body })
export const closePurchase = (accessToken, id, body) => request(poPath(id) + '/close', { method: 'POST', accessToken, body })
