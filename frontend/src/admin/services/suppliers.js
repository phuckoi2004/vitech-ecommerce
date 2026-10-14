import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'

const PATH = '/admin/suppliers'
const BATCH_SIZE = 100

// The current API has pagination and active_only, but no keyword/inactive filter.
// Read every page before filtering in the admin UI; never treat a partial read as a complete directory.
export async function getSupplierDirectory(accessToken, signal) {
  const first = await getAdminData(accessToken, PATH, { active_only: false, page: 1, page_size: BATCH_SIZE }, signal)
  signal?.throwIfAborted()
  const rows = [...first.Items]
  const pages = Math.ceil(first.Total / BATCH_SIZE)
  for (let page = 2; page <= pages; page += 4) {
    signal?.throwIfAborted()
    const numbers = Array.from({ length: Math.min(4, pages - page + 1) }, (_, index) => page + index)
    const results = await Promise.allSettled(numbers.map((number) => getAdminData(accessToken, PATH, { active_only: false, page: number, page_size: BATCH_SIZE }, signal)))
    signal?.throwIfAborted()
    const sessionFailure = results.find((result) => result.status === 'rejected' && [401, 403].includes(result.reason.status))
    if (sessionFailure) throw sessionFailure.reason
    const failure = results.find((result) => result.status === 'rejected')
    if (failure) throw failure.reason
    for (const result of results) rows.push(...result.value.Items)
  }
  return [...new Map(rows.map((row) => [row.SupplierId, row])).values()]
}

export const createSupplier = (accessToken, body) => request(PATH, { method: 'POST', accessToken, body })
export const updateSupplier = (accessToken, id, body) => request(PATH + '/' + encodeURIComponent(id), { method: 'PATCH', accessToken, body })
// Figma's Xóa is soft deletion. Keep supplier references in purchasing/warranty records intact.
export const hideSupplier = (accessToken, id) => updateSupplier(accessToken, id, { IsActive: false })
