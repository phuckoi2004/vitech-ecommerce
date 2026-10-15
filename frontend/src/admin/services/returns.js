import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'
import { purchaseReadBatch } from './purchases.js'

const PATH = '/admin/return-requests'
export async function getReturnDirectory(token, signal) {
  // Search and date filters are local; read the complete directory before sorting
  // and pagination so a waiting request on a later API page is still pinned first.
  const query = { page_size: 100, pending_first: true }
  const first = await getAdminData(token, PATH, { ...query, page: 1 }, signal)
  signal?.throwIfAborted()
  const pages = Array.from({ length: Math.max(0, Math.ceil(first.Total / 100) - 1) }, (_, index) => index + 2)
  const rest = await purchaseReadBatch(pages, (page) => getAdminData(token, PATH, { ...query, page }, signal), signal)
  return [...new Map([...first.Items, ...rest.flatMap((page) => page.Items)].map((row) => [row.ReturnRequestId, row])).values()]
}
export const getReturnDetail = (token, id, signal) => getAdminData(token, PATH + '/' + encodeURIComponent(id), {}, signal)

// Only existing server transitions are exposed; the admin has no customer-cancel action.
export const acceptReturn = (token, id) => request(PATH + '/' + encodeURIComponent(id) + '/accept', { method: 'POST', accessToken: token, body: {} })
export const rejectReturn = (token, id, reason) => request(PATH + '/' + encodeURIComponent(id) + '/reject', { method: 'POST', accessToken: token, body: { Reason: reason } })
export const startReturnReceiving = (token, id) => request(PATH + '/' + encodeURIComponent(id) + '/start-receiving', { method: 'POST', accessToken: token, body: {} })
export const receiveReturn = (token, id) => request(PATH + '/' + encodeURIComponent(id) + '/receive', { method: 'POST', accessToken: token, body: {} })
export const advanceReturn = (token, id, expectedStatus) => request(PATH + '/' + encodeURIComponent(id) + '/advance', { method: 'POST', accessToken: token, body: { ExpectedStatus: expectedStatus } })
