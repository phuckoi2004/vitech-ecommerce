import { request } from './client.js'

export const createCatalogItem = (accessToken, body) => request('/admin/catalog-items', { method: 'POST', accessToken, body })
export const updateCatalogItem = (accessToken, id, body) => request(`/admin/catalog-items/${encodeURIComponent(id)}`, { method: 'PUT', accessToken, body })
export const updateCatalogProduct = (accessToken, id, body) => request(`/admin/catalog-products/${encodeURIComponent(id)}`, { method: 'PUT', accessToken, body })

export const createProduct = (accessToken, body) => request('/admin/products', { method: 'POST', accessToken, body })
export const updateProduct = (accessToken, id, body) => request(`/admin/products/${encodeURIComponent(id)}`, { method: 'PATCH', accessToken, body })
export const deleteProduct = (accessToken, id) => request(`/admin/products/${encodeURIComponent(id)}`, { method: 'DELETE', accessToken })
export const createVariant = (accessToken, body) => request('/admin/variants', { method: 'POST', accessToken, body })
export const updateVariant = (accessToken, id, body) => request(`/admin/variants/${encodeURIComponent(id)}`, { method: 'PATCH', accessToken, body })
export const deleteVariant = (accessToken, id) => request(`/admin/variants/${encodeURIComponent(id)}`, { method: 'DELETE', accessToken })
export const addProductImage = (accessToken, id, body) => request(`/admin/products/${encodeURIComponent(id)}/images`, { method: 'POST', accessToken, body })
export const deleteProductImage = (accessToken, id, imageId) => request(`/admin/products/${encodeURIComponent(id)}/images/${encodeURIComponent(imageId)}`, { method: 'DELETE', accessToken })
