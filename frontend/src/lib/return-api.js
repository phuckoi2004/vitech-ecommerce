import { request } from '../services/api/client.js'

export const listMyReturns = (accessToken, query = {}, { signal } = {}) =>
  request('/return-requests', { accessToken, query, signal })
export const getMyReturn = (accessToken, id, { signal } = {}) =>
  request(`/return-requests/${encodeURIComponent(id)}`, { accessToken, signal })
export const createReturn = (accessToken, body) =>
  request('/return-requests', { method: 'POST', accessToken, body })
export const cancelReturn = (accessToken, id) =>
  request(`/return-requests/${encodeURIComponent(id)}/cancel`, { method: 'POST', accessToken })
export const getReturnItems = (accessToken, orderId, { signal } = {}) =>
  request(`/orders/${encodeURIComponent(orderId)}/return-items`, { accessToken, signal })
export const uploadReturnImage = (accessToken, file) =>
  request('/service-request-image-uploads', { method: 'POST', accessToken, file })
