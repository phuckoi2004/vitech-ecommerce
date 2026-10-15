import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'
import { purchaseReadBatch } from './purchases.js'

const PATH = '/admin/warranty-requests'
export async function getWarrantyDirectory(token, signal) {
  // Read all pages before filtering UI stages, searching serials and paginating.
  const first = await getAdminData(token, PATH, { page_size: 100, page: 1 }, signal)
  signal?.throwIfAborted()
  const pages = Array.from({ length: Math.max(0, Math.ceil(first.Total / 100) - 1) }, (_, index) => index + 2)
  const rest = await purchaseReadBatch(pages, (page) => getAdminData(token, PATH, { page_size: 100, page }, signal), signal)
  return [...new Map([...first.Items, ...rest.flatMap((page) => page.Items)].map((row) => [row.WarrantyRequestId, row])).values()]
}
export const getWarrantyDetail = (token, id, signal) => getAdminData(token, PATH + '/' + encodeURIComponent(id), {}, signal)
export const advanceWarranty = (token, id, body) => request(PATH + '/' + encodeURIComponent(id) + '/advance', { method: 'POST', accessToken: token, body })
export const rejectWarranty = (token, id, reason) => request(PATH + '/' + encodeURIComponent(id) + '/reject', { method: 'POST', accessToken: token, body: { Reason: reason } })
