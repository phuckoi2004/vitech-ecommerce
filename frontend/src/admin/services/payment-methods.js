import { getAdminData } from '../../services/api/admin.js'
import { request } from '../../services/api/client.js'

const PATH = '/admin/payment-methods'
const methodPath = (id) => PATH + '/' + encodeURIComponent(id)
// The complete ordered array includes inactive methods for internal management.
export const getPaymentMethods = (token, signal) => getAdminData(token, '/payment-methods', { active_only: false }, signal)
export const createPaymentMethod = (accessToken, body) => request(PATH, { method: 'POST', accessToken, body })
export const updatePaymentMethod = (accessToken, id, body) => request(methodPath(id), { method: 'PATCH', accessToken, body })
export const deletePaymentMethod = (accessToken, id) => request(methodPath(id), { method: 'DELETE', accessToken })
