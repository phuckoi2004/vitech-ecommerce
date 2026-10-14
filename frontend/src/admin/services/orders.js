import { request } from '../../services/api/client.js'

const orderPath = (id) => '/admin/orders/' + encodeURIComponent(id)
export const updateOrderStatus = (accessToken, id, body) => request(orderPath(id) + '/status', { method: 'POST', accessToken, body })
export const confirmCodDelivery = (accessToken, id, body) => request(orderPath(id) + '/confirm-cod-delivery', { method: 'POST', accessToken, body })
export const updateOrderNote = (accessToken, id, body) => request(orderPath(id), { method: 'PATCH', accessToken, body })
export const assignOrderSerials = (accessToken, id, body) => request(orderPath(id) + '/serials', { method: 'POST', accessToken, body })
export const releaseOrderSerial = (accessToken, id, number) => request(orderPath(id) + '/serials/' + encodeURIComponent(number), { method: 'DELETE', accessToken })
