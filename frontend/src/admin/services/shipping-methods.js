import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'

const path = (id) => '/admin/shipping-methods/' + encodeURIComponent(id)
export const getShippingMethods = (token, signal) => getAdminData(token, '/shipping-methods', { active_only: false }, signal)
export const createShippingMethod = (token, body) => request('/admin/shipping-methods', { method: 'POST', accessToken: token, body })
export const updateShippingMethod = (token, id, body) => request(path(id), { method: 'PATCH', accessToken: token, body })
