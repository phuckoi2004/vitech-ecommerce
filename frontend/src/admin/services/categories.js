import { request } from '../../services/api/client.js'

export const createCategory = (accessToken, body) => request('/admin/categories', { method: 'POST', accessToken, body })
export const updateCategory = (accessToken, id, body) => request('/admin/categories/' + encodeURIComponent(id), { method: 'PATCH', accessToken, body })
export const deleteCategory = (accessToken, id) => request('/admin/categories/' + encodeURIComponent(id), { method: 'DELETE', accessToken })
