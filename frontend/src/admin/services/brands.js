import { request } from '../../services/api/client.js'

export const createBrand = (accessToken, body) => request('/admin/brands', { method: 'POST', accessToken, body })
export const updateBrand = (accessToken, id, body) => request('/admin/brands/' + encodeURIComponent(id), { method: 'PATCH', accessToken, body })
export const deleteBrand = (accessToken, id) => request('/admin/brands/' + encodeURIComponent(id), { method: 'DELETE', accessToken })
