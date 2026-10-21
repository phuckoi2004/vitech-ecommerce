import { request } from '../services/api/client.js'

export const listMyWarranties = (accessToken, query = {}, { signal } = {}) =>
  request('/warranty-requests', { accessToken, query, signal })
export const getMyWarranty = (accessToken, id, { signal } = {}) =>
  request(`/warranty-requests/${encodeURIComponent(id)}`, { accessToken, signal })
export const createWarranty = (accessToken, body) =>
  request('/warranty-requests', { method: 'POST', accessToken, body })
export const cancelWarranty = (accessToken, id) =>
  request(`/warranty-requests/${encodeURIComponent(id)}/cancel`, { method: 'POST', accessToken })
export const getWarrantyItems = (accessToken, orderId, { signal } = {}) =>
  request(`/orders/${encodeURIComponent(orderId)}/warranty-items`, { accessToken, signal })
export const uploadWarrantyImage = (accessToken, file) =>
  request('/service-request-image-uploads', { method: 'POST', accessToken, file })
