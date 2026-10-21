import { request } from '../../services/api/client.js'

const variantPath = (id) => '/admin/variants/' + encodeURIComponent(id)
export const setStockQuantity = (accessToken, id, body) => request(variantPath(id) + '/stock', { method: 'PATCH', accessToken, body })
